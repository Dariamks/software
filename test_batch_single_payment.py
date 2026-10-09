import tempfile
import unittest
from pathlib import Path
from batch_single_payment import read_input_rows

class InputReaderTests(unittest.TestCase):
    def test_reads_supplied_xlsx(self):
        path = '/Users/sea/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_l80ax71b7s3l22_0cfc/temp/drag/新建 XLSX 工作表.xlsx'
        rows = read_input_rows(path)
        self.assertEqual(len(rows), 1101)
        self.assertEqual(rows[0].contract_no, 'IF260107223925794024')
        self.assertEqual(rows[0].cert_id, '432922198109060038')

if __name__ == '__main__':
    unittest.main()
