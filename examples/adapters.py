from kankakee import Adapter, NetUtil

print("Testing adapter capabilities")

netutil = NetUtil()
adapters = netutil.getAllAdapters()
for adapter in adapters:
    print("--------------------")
    print(adapter.name)
    print(adapter.description)
    print(adapter.ip_address)
    print(adapter.gateway)
    print(adapter.broadcast)
    print(adapter.netmask)
    print(adapter.dns)
    print(adapter.mac_address)
    print(adapter.type)
    print(adapter.up)
    print(adapter.dhcp)
    print(adapter.priority)