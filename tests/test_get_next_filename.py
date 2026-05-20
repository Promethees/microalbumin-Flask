import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from get_next_filename import get_next_filename


def test_empty_list_returns_001():
    assert get_next_filename('.csv', [], 'data') == 'data_001.csv'


def test_existing_file_increments():
    files = ['data_001.csv']
    assert get_next_filename('.csv', files, 'data') == 'data_002.csv'


def test_gap_in_sequence_uses_max_plus_one():
    # 001 and 003 present → next is 004
    files = ['data_001.csv', 'data_003.csv']
    assert get_next_filename('.csv', files, 'data') == 'data_004.csv'


def test_different_base_not_counted():
    files = ['other_005.csv']
    assert get_next_filename('.csv', files, 'data') == 'data_001.csv'


def test_different_extension_not_counted():
    files = ['data_005.json']
    assert get_next_filename('.csv', files, 'data') == 'data_001.csv'


def test_wrong_format_not_counted():
    # Filename doesn't match pattern base_NNN.ext
    files = ['data_99.csv', 'data_abc.csv']
    assert get_next_filename('.csv', files, 'data') == 'data_001.csv'


def test_large_sequence_number_pads_correctly():
    files = [f'data_{i:03d}.csv' for i in range(1, 100)]
    assert get_next_filename('.csv', files, 'data') == 'data_100.csv'


@pytest.mark.parametrize('ext', ['.csv', '.json', '.txt'])
def test_extension_respected(ext):
    result = get_next_filename(ext, [], 'base')
    assert result.endswith(ext)
