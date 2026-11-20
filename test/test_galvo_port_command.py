import unittest

from test import bootstrap


class TestGalvoPortCommand(unittest.TestCase):
    def test_port_bit_range(self):
        kernel = bootstrap.bootstrap()
        try:
            kernel.console("service device start -i balor 0\n")
            kernel.device.mock = True
            con = kernel.device.driver.connection
            kernel.console("port on 3\n")
            self.assertEqual(con._port_bits, 1 << 3)
            # Out of range: previously set bit 16 and crashed in struct.pack.
            kernel.console("port on 16\n")
            kernel.console("port on -1\n")
            self.assertEqual(con._port_bits, 1 << 3)
            kernel.console("port off 3\n")
            self.assertEqual(con._port_bits, 0)
        finally:
            kernel()


if __name__ == "__main__":
    unittest.main()
