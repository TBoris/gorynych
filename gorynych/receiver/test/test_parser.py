'''
Tests for message parsers.
Then using this file subclass all test cases from ParserTest and put parser
instance in setUp method in a field self.parser.
'''
import unittest

from zope.interface.verify import verifyObject

from gorynych.receiver.parsers import IParseMessage, GlobalSatTR203, \
    TeltonikaGH3000UDP


class ParserTest(unittest.TestCase):

    def test_parsed_interface(self):
        if hasattr(self, 'parser'):
            verifyObject(IParseMessage, self.parser)

    def _return_type_and_fields(self, result):
        self.assertIsInstance(result, dict)
        for item in ['lat', 'lon', 'imei', 'ts', 'alt']:
            self.assertIn(item, result.keys())

    def _check_values(self, result, **kwargs):
        self.assertTrue(result.has_key('alt'))
        self.assertTrue(result.has_key('lat'))
        self.assertTrue(result.has_key('lon'))
        self.assertTrue(result.has_key('ts'))
        self.assertTrue(result.has_key('imei'))
        self.assertTrue(result.has_key('h_speed'))
        self.assertDictContainsSubset(kwargs, result)


class GlobalSatTR203Test(ParserTest):

    def setUp(self):
        self.parser = GlobalSatTR203()

    def test_parse(self):
        message = 'GSr,011412001274897,3,3,00,,3,090713,081527,E02445.3853,N4239.2928,546,0.09,318,8,1.3,93,284,01,0e74,0f74,12,24*60!'
        result = self.parser.parse(message)
        print result
        self._return_type_and_fields(result)
        self._check_values(result, h_speed=0.1, battery='93', lon=24.756421,
                           lat=42.65488, imei='011412001274897', alt=546)

    def test_correct_checksum(self):
        message = 'GSr,011412001415649,3,3,00,,3,090713,081447,E02445.3951,N4239.2872,536,0.27,28,5,7.2,93,284,01,0e74,0f74,12,27*54!'
        result = self.parser.check_message_correctness(message)
        self.assertEqual(message, result)

    def test_incorrect_checksum(self):
        message = 'GSr,011412001274897,3,3,00,,3,090713,081502,E02445.3855,N4239.2920,546,0.29,316,7,1.4,93,284,01,0e74,0f74,12,26*4f!'
        self.assertRaises(ValueError,
                          self.parser.check_message_correctness, message)


class TeltonikaGH3000UDPTest(ParserTest):

    def setUp(self):
        self.parser = TeltonikaGH3000UDP()
        self.message = message = "003c00000102000F313233343536373839303132333435070441bf9db00fff425adbd741ca6e1e009e1205070001030b160000601a02015e02000314006615000a160067010500000ce441bf9d920fff425adbb141ca6fc900a2b218070001030b160000601a02015e02000314006615000a160067010500000cc641bf9d740fff425adbee41ca739200b6c91e070001030b1f0000601a02015f02000314006615000a160066010500000ca841bf9cfc0fff425adba041ca70c100b93813070001030b1f0000601a02015f02000314002315000a160025010500000c3004".decode(
            'hex')

    def test_parse(self):
        result = self.parser.parse(self.message)
        self._check_values(result, h_speed=5, lon=25.303768,
                           lat=54.714687, imei='123456789012345', alt=158)

    def test_response(self):
        self.parser.parse(self.message)
        response = self.parser.get_response()
        self.assertEqual(response.encode('hex'), '00050002010204')

if __name__ == '__main__':
    unittest.main()