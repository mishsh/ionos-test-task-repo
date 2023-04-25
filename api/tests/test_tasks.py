from multiprocessing.pool import ThreadPool
import sys
import threading
from time import sleep
from unittest import skipIf
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.db import connection

from api.models import TestEnvironment, TestRunRequest, TestFilePath
from api.tasks import handle_task_retry, MAX_RETRY, execute_test_run_request


class TestTasks(TestCase):

    def setUp(self) -> None:
        self.env = TestEnvironment.objects.create(name='my_env')
        self.test_run_req = TestRunRequest.objects.create(requested_by='Ramadan', env=self.env)
        self.path1 = TestFilePath.objects.create(path='path1')
        self.path2 = TestFilePath.objects.create(path='path2')
        self.test_run_req.path.add(self.path1)
        self.test_run_req.path.add(self.path2)

    @patch('api.tasks.execute_test_run_request.s')
    def test_handle_task_retry_less_than_max_retry(self, task_mock):
        handle_task_retry(self.test_run_req, MAX_RETRY - 1)
        self.assertEqual(TestRunRequest.StatusChoices.RETRYING.name, self.test_run_req.status)
        self.assertEqual(f'\nFailed to run tests on env my_env retrying in 512 seconds.', self.test_run_req.logs)
        self.assertTrue(task_mock.called)
        task_mock.assert_called_with(self.test_run_req.id, MAX_RETRY)

    def test_handle_task_retry_equal_to_max_retry(self):
        handle_task_retry(self.test_run_req, MAX_RETRY)
        self.assertEqual(TestRunRequest.StatusChoices.FAILED_TO_START.name, self.test_run_req.status)
        self.assertEqual(f'\nFailed to run tests on env my_env after retrying 10 times.', self.test_run_req.logs)

    @patch('api.tasks.handle_task_retry')
    def test_execute_test_run_request_busy_env(self, retry):
        self.env.status = TestEnvironment.StatusChoices.BUSY.name
        self.env.save()
        execute_test_run_request(self.test_run_req.id)
        self.assertTrue(retry.called)
        retry.assert_called_with(self.test_run_req, 0)

    @patch('subprocess.Popen.wait', return_value=1)
    def test_execute_test_run_request_failed(self, wait):
        execute_test_run_request(self.test_run_req.id)
        self.test_run_req.refresh_from_db()
        self.assertTrue(wait.called)
        wait.assert_called_with(timeout=settings.TEST_RUN_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(TestRunRequest.StatusChoices.FAILED.name, self.test_run_req.status)

    @patch('subprocess.Popen.wait', return_value=0)
    def test_execute_test_run_request_success(self, wait):
        execute_test_run_request(self.test_run_req.id)
        self.test_run_req.refresh_from_db()
        self.assertTrue(wait.called)
        wait.assert_called_with(timeout=settings.TEST_RUN_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(TestRunRequest.StatusChoices.SUCCESS.name, self.test_run_req.status)


class ReturnValueThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = None

    def run(self):
        if self._target is None:
            return
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as exc:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)
        return self.result


class TestTasksAtomicityUsingEvents(TransactionTestCase):
    def setUp(self):
        self.lock_event = threading.Event()
        self.unlock_event = threading.Event()

        original_lock = TestEnvironment.lock
        def patched_lock(_self):
            original_lock(_self)
            self.lock_event.set()
        TestEnvironment.lock = patched_lock

        self.original_lock = original_lock

        original_unlock = TestEnvironment.unlock
        def patched_unlock(_self):
            sleep(0.2)
            original_unlock(_self)
            self.unlock_event.set()
        TestEnvironment.unlock = patched_unlock

        self.original_unlock = original_unlock


    def tearDown(self):
        TestEnvironment.lock = self.original_lock
        TestEnvironment.unlock = self.original_unlock


    @skipIf(threading is None, "Test requires threading")
    @patch('subprocess.Popen.wait', return_value=0)
    @patch('api.tasks.handle_task_retry')
    def test_env_runs_tests_sequentially(self, _, retry):
        env = TestEnvironment.objects.create(name='atomic_env')
        path1 = TestFilePath.objects.create(path='path13')
        
        def create_test_run() -> TestRunRequest:
            run = TestRunRequest.objects.create(requested_by='Tester', env=env)
            run.path.add(path1)
            return run

        def func(run: TestRunRequest):
            execute_test_run_request(run.id)
            connection.close()
        

        first = create_test_run()
        second = create_test_run()
        
        th1 = ReturnValueThread(target=func, args=(first,))
        th2 = ReturnValueThread(target=func, args=(second,))
        th3 = ReturnValueThread(target=func, args=(second,))


        th1.start()

        self.lock_event.wait()
        th2.start() # wait 1st lock and try to lock from 2nd thread (should fail)

        self.unlock_event.wait()
        self.assertTrue(retry.called_once) # retry already called by the time of unlock
        self.lock_event.clear()
        th3.start()  # after unlock event new lock is possible

        th1.join()
        th2.join()
        th3.join()

        self.assertTrue(self.lock_event.is_set())
