import unittest

from gorynych.info.domain import transport
from gorynych.info.domain.ids import TransportID


def create_transport(id, type='bUs   ', title='   yELlow bus',
                     description=None):
    tr = transport.TransportFactory().create_transport(id, type, title,
                                                            description)
    return tr


class TransportFactoryTest(unittest.TestCase):
    def setUp(self):
        self.skipTest("Transport is not number one priority.")

    def test_creation(self):
        trans = create_transport(TransportID(15))
        self.assertEqual(trans.id, TransportID(15))
        self.assertEqual(trans.type, 'bus')
        self.assertEqual(trans.title, 'Yellow bus')
        self.assertIsNone(trans.description)

        trans = create_transport(TransportID(1), description='one')
        self.assertEqual(trans.id, TransportID(1))
        self.assertEqual(trans.description, 'One')

    def test_incorrect_creation(self):
        self.assertRaises(ValueError, create_transport, 15, type='drdr')


if __name__ == '__main__':
    unittest.main()
