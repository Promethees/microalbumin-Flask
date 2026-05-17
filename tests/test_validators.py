import unittest
import sys
import os

# Add src to path so we can import validators
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from validators import validate_csv_content, validate_json_content

class TestValidators(unittest.TestCase):
    def test_validate_csv_kinetics_legal(self):
        legal_kinetics = """# Measurement: ABSORBANCE
# MeasUnit: AU
# TimeUnit: minute
# MeasMode: kinetics
Concentration,maxRate,Slope,Sat,Time To Sat
0,0.1,0.01,0.5,10
10,0.2,0.02,0.6,20
"""
        success, result = validate_csv_content(legal_kinetics)
        self.assertTrue(success)

    def test_validate_csv_point_legal(self):
        legal_point = """# Measurement: ABSORBANCE
# MeasUnit: AU
# TimeUnit: minute
# MeasMode: point
Concentration,Value,TimePoint
0,0.15,2
10,0.25,2
"""
        success, result = validate_csv_content(legal_point)
        self.assertTrue(success)

    def test_validate_csv_pattern4_legal(self):
        legal_pattern4 = """# Measurement: ABSORBANCE
# Unit: NONE
# Concentration: NONE
Timestamp,Value:1,Value:2
0,0.1,0.2
15,0.11,0.21
"""
        success, result = validate_csv_content(legal_pattern4)
        self.assertTrue(success)

    def test_validate_csv_invalid_header(self):
        invalid_csv = "Invalid,Header,Raw\n0,1,2"
        success, result = validate_csv_content(invalid_csv)
        self.assertFalse(success)
        self.assertIn("Invalid CSV header", result)

    def test_validate_csv_missing_metadata(self):
        missing_meta = "Concentration,maxRate,Slope,Sat,Time To Sat\n0,0.1,0.01,0.5,10"
        success, result = validate_csv_content(missing_meta)
        self.assertFalse(success)
        self.assertIn("Metadata must include", result)

    def test_validate_json_legal(self):
        legal_json = '{"key": "value", "list": [1, 2, 3]}'
        success, result = validate_json_content(legal_json)
        self.assertTrue(success)

    def test_validate_json_illegal(self):
        illegal_json = '{"key": "value", "list": [1, 2, 3]'
        success, result = validate_json_content(illegal_json)
        self.assertFalse(success)
        self.assertIn("Invalid JSON format", result)

if __name__ == '__main__':
    unittest.main()
