import unittest
from unittest.mock import patch, MagicMock
from app.services.sophos_service import SophosService

SAMPLE_SFOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Response APIVersion="2100.1">
  <Login>
    <status>Authentication Successful</status>
  </Login>
  <Interface>
    <Name>Port1_LAN</Name>
    <Hardware>eth0</Hardware>
    <IPAddress>10.1.1.2</IPAddress>
    <Netmask>255.255.255.0</Netmask>
    <InterfaceStatus>ON</InterfaceStatus>
    <NetworkZone>LAN</NetworkZone>
    <Status>Connected</Status>
  </Interface>
  <FirewallRule>
    <Name>Allow_LAN_WAN</Name>
    <Status>Enable</Status>
    <NetworkPolicy>
      <Action>Accept</Action>
      <SourceZones><Zone>LAN</Zone></SourceZones>
      <DestinationZones><Zone>WAN</Zone></DestinationZones>
    </NetworkPolicy>
  </FirewallRule>
  <FirewallRule>
    <Name>Block_Malicious_IPs</Name>
    <Status>Enable</Status>
    <NetworkPolicy>
      <Action>Drop</Action>
      <SourceZones><Zone>WAN</Zone></SourceZones>
      <DestinationZones><Zone>LAN</Zone></DestinationZones>
    </NetworkPolicy>
  </FirewallRule>
  <IPHostGroup>
    <Name>Malicious_Blacklist</Name>
    <Description>Auto blocked hosts</Description>
    <HostList>
      <Host>198.51.100.10</Host>
      <Host>198.51.100.11</Host>
    </HostList>
  </IPHostGroup>
</Response>"""

class TestSophosService(unittest.TestCase):
    def setUp(self):
        SophosService._cache.clear()

    @patch.object(SophosService, '_make_request')
    def test_get_firewall_overview_success(self, mock_make_request):
        mock_make_request.return_value = SAMPLE_SFOS_XML
        
        overview = SophosService.get_firewall_overview(force=True)
        self.assertTrue(overview["success"])
        self.assertEqual(overview["auth_status"], "Authentication Successful")
        self.assertEqual(overview["stats"]["interfaces_total"], 1)
        self.assertEqual(overview["stats"]["interfaces_up"], 1)
        self.assertEqual(overview["stats"]["rules_total"], 2)
        self.assertEqual(overview["stats"]["rules_accept"], 1)
        self.assertEqual(overview["stats"]["rules_drop"], 1)
        self.assertEqual(overview["stats"]["host_groups_total"], 1)
        self.assertEqual(overview["host_groups"][0]["hosts_count"], 2)

    @patch.object(SophosService, '_make_request')
    def test_get_firewall_overview_caching(self, mock_make_request):
        mock_make_request.return_value = SAMPLE_SFOS_XML
        
        # First call hits _make_request
        r1 = SophosService.get_firewall_overview(force=False)
        self.assertEqual(mock_make_request.call_count, 1)
        
        # Second call should use cache
        r2 = SophosService.get_firewall_overview(force=False)
        self.assertEqual(mock_make_request.call_count, 1)
        self.assertEqual(r1, r2)
        
        # Third call with force=True invalidates cache
        r3 = SophosService.get_firewall_overview(force=True)
        self.assertEqual(mock_make_request.call_count, 2)

    @patch.object(SophosService, '_make_request')
    def test_get_firewall_overview_error_handling(self, mock_make_request):
        mock_make_request.side_effect = Exception("Connection timeout")
        
        overview = SophosService.get_firewall_overview(force=True)
        self.assertFalse(overview["success"])
        self.assertIn("Connection timeout", overview["error"])
        self.assertEqual(overview["auth_status"], "Failed")
        self.assertEqual(overview["stats"]["rules_total"], 0)

if __name__ == '__main__':
    unittest.main()
