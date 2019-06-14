import io
import json
import os
import re
import sys
import unittest
from collections import namedtuple

from mock import MagicMock
from mock import patch

from truffleHog import truffleHog


class TestStringMethods(unittest.TestCase):

    def test_shannon(self):
        random_string_b64 = "ZWVTjPQSdhwRgl204Hc51YCsritMIzn8B=/p9UyeX7xu6KkAGqfm3FJ+oObLDNEva"
        random_string_hex = "b3A0a1FDfe86dcCE945B72"
        self.assertGreater(truffleHog.shannon_entropy(random_string_b64, truffleHog.BASE64_CHARS), 4.5)
        self.assertGreater(truffleHog.shannon_entropy(random_string_hex, truffleHog.HEX_CHARS), 3)

    def test_cloning(self):
        project_path = truffleHog.clone_git_repo("https://github.com/dxa4481/truffleHog.git")
        license_file = os.path.join(project_path, "LICENSE")
        self.assertTrue(os.path.isfile(license_file))

    def test_unicode_expection(self):
        try:
            truffleHog.find_strings("https://github.com/dxa4481/tst.git")
        except UnicodeEncodeError:
            self.fail("Unicode print error")

    def test_return_correct_commit_hash(self):
        # Start at commit d15627104d07846ac2914a976e8e347a663bbd9b, which
        # is immediately followed by a secret inserting commit:
        # https://github.com/dxa4481/truffleHog/commit/9ed54617547cfca783e0f81f8dc5c927e3d1e345
        since_commit = 'd15627104d07846ac2914a976e8e347a663bbd9b'
        commit_w_secret = '9ed54617547cfca783e0f81f8dc5c927e3d1e345'
        xcheck_commit_w_scrt_comment = 'OH no a secret'

        if sys.version_info >= (3,):
            tmp_stdout = io.StringIO()
        else:
            tmp_stdout = io.BytesIO()
        bak_stdout = sys.stdout

        # Redirect STDOUT, run scan and re-establish STDOUT
        sys.stdout = tmp_stdout
        try:
            truffleHog.find_strings("https://github.com/dxa4481/truffleHog.git",
                                    since_commit=since_commit, print_json=True, suppress_output=False)
        finally:
            sys.stdout = bak_stdout

        json_result_list = tmp_stdout.getvalue().split('\n')
        results = [json.loads(r) for r in json_result_list if bool(r.strip())]
        filtered_results = [result for result in results if result['commitHash'] == commit_w_secret]
        self.assertEqual(1, len(filtered_results))
        self.assertEqual(commit_w_secret, filtered_results[0]['commitHash'])
        # Additionally, we cross-validate the commit comment matches the expected comment
        self.assertEqual(xcheck_commit_w_scrt_comment, filtered_results[0]['commit'].strip())

    # noinspection PyUnusedLocal
    @patch('truffleHog.truffleHog.clone_git_repo')
    @patch('truffleHog.truffleHog.Repo')
    @patch('shutil.rmtree')
    def test_branch(self, rmtree_mock, repo_const_mock, clone_git_repo):  # pylint: disable=unused-argument
        repo = MagicMock()
        repo_const_mock.return_value = repo
        truffleHog.find_strings("test_repo", branch="testbranch")
        self.assertIsNone(repo.remotes.origin.fetch.assert_called_once_with("testbranch"))

    def test_path_included(self):
        blob = namedtuple('Blob', ('a_path', 'b_path'))
        blobs = {
            'file-root-dir': blob('file', 'file'),
            'file-sub-dir': blob('sub-dir/file', 'sub-dir/file'),
            'new-file-root-dir': blob(None, 'new-file'),
            'new-file-sub-dir': blob(None, 'sub-dir/new-file'),
            'deleted-file-root-dir': blob('deleted-file', None),
            'deleted-file-sub-dir': blob('sub-dir/deleted-file', None),
            'renamed-file-root-dir': blob('file', 'renamed-file'),
            'renamed-file-sub-dir': blob('sub-dir/file', 'sub-dir/renamed-file'),
            'moved-file-root-dir-to-sub-dir': blob('moved-file', 'sub-dir/moved-file'),
            'moved-file-sub-dir-to-root-dir': blob('sub-dir/moved-file', 'moved-file'),
            'moved-file-sub-dir-to-sub-dir': blob('sub-dir/moved-file', 'moved/moved-file'),
        }
        src_paths = set(blob.a_path for blob in blobs.values() if blob.a_path is not None)
        dest_paths = set(blob.b_path for blob in blobs.values() if blob.b_path is not None)
        all_paths = src_paths.union(dest_paths)
        all_paths_patterns = [re.compile(re.escape(p)) for p in all_paths]
        overlap_patterns = [re.compile(r'sub-dir/.*'), re.compile(r'moved/'), re.compile(r'[^/]*file$')]
        sub_dirs_patterns = [re.compile(r'.+/.+')]
        deleted_paths_patterns = [re.compile(r'(.*/)?deleted-file$')]
        for name, blob in blobs.items():
            self.assertTrue(truffleHog.path_included(blob),
                            '{} should be included by default'.format(blob))
            self.assertTrue(truffleHog.path_included(blob, include_patterns=all_paths_patterns),
                            '{} should be included with include_patterns: {}'.format(blob, all_paths_patterns))
            self.assertFalse(truffleHog.path_included(blob, exclude_patterns=all_paths_patterns),
                             '{} should be excluded with exclude_patterns: {}'.format(blob, all_paths_patterns))
            self.assertFalse(truffleHog.path_included(blob,
                                                      include_patterns=all_paths_patterns,
                                                      exclude_patterns=all_paths_patterns),
                             '{} should be excluded with overlapping patterns: \n\tinclude: '
                             '{include_patterns}\n\texclude: {exclude_patterns}'.format(
                                 blob, include_patterns=all_paths_patterns, exclude_patterns=all_paths_patterns))
            self.assertFalse(truffleHog.path_included(blob,
                                                      include_patterns=overlap_patterns,
                                                      exclude_patterns=all_paths_patterns),
                             '{} should be excluded with overlapping patterns: \n\tinclude: {}\n\texclude: {}'.format(
                                 blob, overlap_patterns, all_paths_patterns))
            self.assertFalse(truffleHog.path_included(blob,
                                                      include_patterns=all_paths_patterns,
                                                      exclude_patterns=overlap_patterns),
                             '{} should be excluded with overlapping patterns: \n\tinclude: {}\n\texclude: {}'.format(
                                 blob, all_paths_patterns, overlap_patterns))
            path = blob.b_path if blob.b_path else blob.a_path
            if '/' in path:
                self.assertTrue(truffleHog.path_included(blob, include_patterns=sub_dirs_patterns),
                                '{}: inclusion should include sub directory paths: {}'.format(blob, sub_dirs_patterns))
                self.assertFalse(truffleHog.path_included(blob, exclude_patterns=sub_dirs_patterns),
                                 '{}: exclusion should exclude sub directory paths: {}'.format(blob, sub_dirs_patterns))
            else:
                self.assertFalse(truffleHog.path_included(blob, include_patterns=sub_dirs_patterns),
                                 '{}: inclusion should exclude root directory paths: {}'.format(blob,
                                                                                                sub_dirs_patterns))
                self.assertTrue(truffleHog.path_included(blob, exclude_patterns=sub_dirs_patterns),
                                '{}: exclusion should include root directory paths: {}'.format(blob, sub_dirs_patterns))
            if name.startswith('deleted-file-'):
                self.assertTrue(truffleHog.path_included(blob, include_patterns=deleted_paths_patterns),
                                '{}: inclusion should match deleted paths: {}'.format(blob, deleted_paths_patterns))
                self.assertFalse(truffleHog.path_included(blob, exclude_patterns=deleted_paths_patterns),
                                 '{}: exclusion should match deleted paths: {}'.format(blob, deleted_paths_patterns))

    # noinspection PyUnusedLocal
    @patch('truffleHog.truffleHog.clone_git_repo')
    @patch('truffleHog.truffleHog.Repo')
    @patch('shutil.rmtree')
    def test_repo_path(self, rmtree_mock, repo_const_mock, clone_git_repo):  # pylint: disable=unused-argument
        truffleHog.find_strings("test_repo", repo_path="test/path/")
        self.assertIsNone(rmtree_mock.assert_not_called())
        self.assertIsNone(clone_git_repo.assert_not_called())


if __name__ == '__main__':
    unittest.main()
