#ifndef MACNETUTIL_HPP
#define MACNETUTIL_HPP

#include <arpa/inet.h>
#include <unistd.h>
#include <ifaddrs.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/sysctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netdb.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/if_media.h>
#include <net/route.h>
#include <netinet/in.h>
#include <math.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <vector>
#include <map>
#include <iomanip>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <SystemConfiguration/SystemConfiguration.h>
#include <CoreFoundation/CoreFoundation.h>
#include <iostream>

// Compute sockaddr padded size (macOS-safe)
#ifndef SA_SIZE
#define SA_SIZE(sa)  \
    ( ((sa)->sa_len > 0) ? \
      (1 + (((sa)->sa_len - 1) | (sizeof(uint32_t) - 1))) : \
      sizeof(uint32_t) )
#endif


namespace kankakee
{

class NetUtil {
public:


    NetUtil() { }
    ~NetUtil() { }

    std::vector<Adapter> getAllAdapters() const {
        std::vector<Adapter> result;

        CFArrayRef ifs = SCNetworkInterfaceCopyAll();
        CFIndex count = CFArrayGetCount(ifs);
        std::cout << "interface count: " << count << std::endl;
        for (CFIndex i = 0; i < count; i++) {
            Adapter adapter;
            SCNetworkInterfaceRef item = (SCNetworkInterfaceRef)CFArrayGetValueAtIndex(ifs, i);
            std::string bsd = getStringFromRef(SCNetworkInterfaceGetBSDName(item));
            std::string displayName = getStringFromRef(SCNetworkInterfaceGetLocalizedDisplayName(item));
            int priority = getInterfacePriority(bsd);
            std::string if_type = getStringFromRef(SCNetworkInterfaceGetInterfaceType(item));
            std::string hardware;
            if (bsd.substr(0, 16) != "com.redhat.spice") {
                // hack around vm interface seg fault
                hardware = getStringFromRef(SCNetworkInterfaceGetHardwareAddressString(item));
            }
            CFArrayRef protocols = SCNetworkInterfaceGetSupportedProtocolTypes(item);
            std::string serviceID = getServiceIDForInterface(bsd);
            bool dhcp = dhcpEnabled(serviceID); 
            bool hasLink = interfaceHasLink(bsd);
            std::string gateway = getGateway(bsd);
            std::string address;
            std::string netmask;
            std::string broadcast;
            std::unordered_map<std::string, std::string> interfaceIPv4 = ipV4(bsd);
            try {
                address = interfaceIPv4.at("Address");
                netmask = interfaceIPv4.at("SubnetMask");
                broadcast = interfaceIPv4.at("BroadcastAddress");
            }
            catch (const std::out_of_range& e) {}
            std::vector<std::string> dns = dnsForService(serviceID);

            adapter.name = bsd;
            adapter.description = displayName;
            adapter.ip_address = address;
            adapter.gateway = gateway;
            adapter.broadcast = broadcast;
            adapter.netmask = netmask;
            adapter.dns = dns;
            adapter.mac_address = hardware;
            adapter.type = if_type;
            adapter.dhcp = dhcp;
            adapter.up = hasLink;
            adapter.priority = priority;
            result.push_back(adapter);
        }
        return result;
    }

    std::map<std::string, int> getActiveNetworkInterfaces() const {
        std::map<std::string, int> result;

        CFArrayRef ifs = SCNetworkInterfaceCopyAll();
        CFIndex count = CFArrayGetCount(ifs);
        std::cout << "interface count: " << count << std::endl;
        for (CFIndex i = 0; i < count; i++) {
            SCNetworkInterfaceRef item = (SCNetworkInterfaceRef)CFArrayGetValueAtIndex(ifs, i);
            std::string bsd = getStringFromRef(SCNetworkInterfaceGetBSDName(item));
            std::string displayName = getStringFromRef(SCNetworkInterfaceGetLocalizedDisplayName(item));
            int priority = getInterfacePriority(bsd);
            std::string if_type = getStringFromRef(SCNetworkInterfaceGetInterfaceType(item));
            std::string hardware = getStringFromRef(SCNetworkInterfaceGetHardwareAddressString(item));
            CFArrayRef protocols = SCNetworkInterfaceGetSupportedProtocolTypes(item);
            std::string serviceID = getServiceIDForInterface(bsd);
            bool dhcp = dhcpEnabled(serviceID); 
            bool hasLink = interfaceHasLink(bsd);
            std::string gateway = getGateway(bsd);
            std::string address;
            std::string netmask;
            std::string broadcast;
            std::unordered_map<std::string, std::string> interfaceIPv4 = ipV4(bsd);
            try {
                address = interfaceIPv4.at("Address");
                netmask = interfaceIPv4.at("SubnetMask");
                broadcast = interfaceIPv4.at("BroadcastAddress");
            }
            catch (const std::out_of_range& e) {}
            std::vector<std::string> dns = dnsForService(serviceID);
            std::cout << "bsd name:   " << bsd << "\n"
                      << "display:    " << displayName << "\n"
                      << "if_type:    " << if_type << "\n"
                      << "priority:   " << (priority < 0 ? "" : std::to_string(priority)) << "\n"
                      << "hardware:   " << hardware << "\n"
                      << "service:    " << serviceID << "\n"
                      << "dhcp:       " << dhcp << "\n"
                      << "address:    " << address << "\n"
                      << "netmask:    " << netmask << "\n"
                      << "broadcast:  " << broadcast << "\n"
                      << "gateway:    " << gateway << "\n"
                      << "status:     " << (hasLink ? "UP" : "DOWN") << "\n";
            for (int j = 0; j < dns.size(); j++)
                std::cout << "dns " << j << ":      " << dns[j] << "\n";
            std::cout << std::endl;
        }
        return result;
    }

    std::string getGateway(const std::string& name) const
    {
        std::string result;
        try {
            std::stringstream cmd;
            cmd << "netstat -rn | grep default | grep ";
            cmd << name;

            std::array<char, 128> buffer;
            std::string response;

            FILE* pipe = popen(cmd.str().c_str(), "r");
            if (!pipe) {
                throw std::runtime_error("popen() failed!");
            }
            try {
                while (std::fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
                    response += buffer.data();
                }
            } catch (const std::exception& e) {
                pclose(pipe);
                throw std::runtime_error(e.what());
            }
            pclose(pipe);

            std::istringstream iss(response);
            std::string word;

            int count = 0;
            while (iss >> word) {
                count++;
                if (count == 2) {
                    result = word;
                    break;
                }
            }
        }
        catch (const std::exception& e) {
            std::cout << "get gateway error: " << e.what() << std::endl;
        }
        return result;
    }

    std::unordered_map<std::string, std::string> ipV4(const std::string& name) const {
        std::string result;
        SCDynamicStoreRef store = nullptr;
        CFStringRef interfaceKey = nullptr;
        CFDictionaryRef interfaceIPv4 = nullptr;
        CFStringRef bsd = nullptr;
        std::unordered_map<std::string, std::string> results;
        try {
            if (name.empty())
                throw std::runtime_error("empty name");

            bsd = CFStringCreateWithCString(kCFAllocatorDefault, name.c_str(), kCFStringEncodingUTF8);

            if (!(interfaceKey = CFStringCreateWithFormat(nullptr, nullptr, CFSTR("State:/Network/Interface/%@/IPv4"), bsd)))
                throw std::runtime_error("CFStringCreateWithFormat returned nullptr");
            
            if (!(interfaceIPv4 = (CFDictionaryRef)SCDynamicStoreCopyValue(store, interfaceKey)))
                throw std::runtime_error("SCDynamicStoreCopyValue returned nullptr");

            CFArrayRef subnetMasks = (CFArrayRef)CFDictionaryGetValue(interfaceIPv4, CFSTR("SubnetMasks"));
            if (CFArrayGetCount(subnetMasks))
                results.insert(std::pair("SubnetMask", getStringFromRef((CFStringRef)CFArrayGetValueAtIndex(subnetMasks, 0))));    

            CFArrayRef addresses = (CFArrayRef)CFDictionaryGetValue(interfaceIPv4, CFSTR("Addresses"));
            if (CFArrayGetCount(addresses))
                results.insert(std::pair("Address", getStringFromRef((CFStringRef)CFArrayGetValueAtIndex(addresses, 0))));

            CFArrayRef broadcastAddresses = (CFArrayRef)CFDictionaryGetValue(interfaceIPv4, CFSTR("BroadcastAddresses"));
            if (CFArrayGetCount(broadcastAddresses))
                results.insert(std::pair("BroadcastAddress", getStringFromRef((CFStringRef)CFArrayGetValueAtIndex(broadcastAddresses, 0))));
        }
        catch (const std::exception& e) {
            if (std::string(e.what()) != "SCDynamicStoreCopyValue returned nullptr")
                std::cout << "ipV4: " << e.what() << std::endl;
        }

        if (store) CFRelease(store);
        if (interfaceIPv4) CFRelease(interfaceIPv4);
        if (interfaceKey) CFRelease(interfaceKey);
        if (bsd) CFRelease(bsd);
        return results;
    }

    int getInterfacePriority(const std::string& name) const
    {
        SCPreferencesRef prefs = nullptr;
        SCNetworkSetRef set = nullptr;
        CFArrayRef order = nullptr;
        int priority = -1;

        try {
            if (name.empty()) 
                throw std::runtime_error("empty name");

            if (!(prefs = SCPreferencesCreate(nullptr, CFSTR("ifprio"), nullptr)))
                throw std::runtime_error("NULL");

            if (!(set = SCNetworkSetCopyCurrent(prefs)))
                throw std::runtime_error("NULL");

            if (!(order = SCNetworkSetGetServiceOrder(set)))
                throw std::runtime_error("NULL");

            for (CFIndex i = 0; i < CFArrayGetCount(order); i++) {
                CFStringRef sid = (CFStringRef)CFArrayGetValueAtIndex(order, i);
                SCNetworkServiceRef service = SCNetworkServiceCopy(prefs, sid);
                SCNetworkInterfaceRef iface = SCNetworkServiceGetInterface(service);
                CFStringRef bsdName = SCNetworkInterfaceGetBSDName(iface);
                if (!bsdName) continue;

                if (name == getStringFromRef(bsdName))
                    priority = i;
            }
        }
        catch (const std::exception& e) {
            std::cout << "getInterfacePriority error: " << e.what() << std::endl;
        }

        if (set) CFRelease(set);
        if (prefs) CFRelease(prefs);
        if (order) CFRelease(order);

        return priority;
    }

    std::string getServiceIDForInterface(const std::string& if_name) const 
    {
        std::string result;
        SCPreferencesRef prefs = nullptr;
        CFArrayRef services = nullptr;

        try {
            if (!(prefs = SCPreferencesCreate(nullptr, CFSTR("NetworkServiceLister"), nullptr)))
                throw std::runtime_error("SCPreferencesCreate return nullptr");
            if (!(services = SCNetworkServiceCopyAll(prefs)))
                throw std::runtime_error("SCNetworkServiceCopyAll returned nullptr");

            CFIndex count = CFArrayGetCount(services);
            for (CFIndex i = 0; i < count; i++) {
                SCNetworkServiceRef service = (SCNetworkServiceRef)CFArrayGetValueAtIndex(services, i);
                CFStringRef serviceID = SCNetworkServiceGetServiceID(service);
                SCNetworkInterfaceRef iface = SCNetworkServiceGetInterface(service);
                if (!iface) continue;
                CFStringRef bsdName = SCNetworkInterfaceGetBSDName(iface);
                if (!bsdName) continue;
                if (if_name == getStringFromRef(bsdName)) {
                    result = getStringFromRef(serviceID);
                }
            }
        }
        catch (const std::exception& e) {
            std::cout << "getServiceIDForInterface error: " << e.what() << std::endl;
        }

        if (prefs) CFRelease(prefs);
        if (services) CFRelease(services);
        return result;
    }

    std::string getStringFromRef(CFStringRef arg) const 
    {
        char buf[1024];
        CFStringGetCString(arg, buf, sizeof(buf), kCFStringEncodingUTF8);
        return buf;
    }

    bool dhcpEnabled(const std::string& serviceID) const
    {
        SCDynamicStoreRef store = nullptr;
        CFDictionaryRef dhcpInfo = nullptr;
        CFStringRef dhcpKey = nullptr;
        bool result = false;

        try {
            if (serviceID.empty())
                throw std::runtime_error("empty service id");

            dhcpKey = CFStringCreateWithFormat(
                nullptr, nullptr,
                CFSTR("State:/Network/Service/%@/DHCP"),
                CFStringCreateWithCString(nullptr, serviceID.c_str(), kCFStringEncodingUTF8)
            );

            if (!(store = SCDynamicStoreCreate(nullptr, CFSTR("dhcp-reader"), nullptr, nullptr)))
                throw std::runtime_error("SCDynamicStoreCreate returned nullptr");
            if (!(dhcpInfo = (CFDictionaryRef)SCDynamicStoreCopyValue(store, dhcpKey)))
                throw std::runtime_error("dhcp returned nullptr");

            result = true;
        }
        catch (const std::exception& e) {
            if ((std::string(e.what()) != "dhcp returned nullptr") && (std::string(e.what()) != "empty service id"))
                std::cout << "dhcpEnabled error: " << e.what() << std::endl;
        }

        if (dhcpInfo) CFRelease(dhcpInfo);
        if (store) CFRelease(store);
        if (dhcpKey) CFRelease(dhcpKey);
        return result;
    }

    bool interfaceHasLink(const std::string& name) const {
        int s = socket(AF_INET, SOCK_DGRAM, 0);
        if (s < 0) return false;

        struct ifmediareq ifm;
        memset(&ifm, 0, sizeof(ifm));
        strncpy(ifm.ifm_name, name.c_str(), sizeof(ifm.ifm_name));

        if (ioctl(s, SIOCGIFMEDIA, &ifm) < 0) {
            close(s);
            return false;
        }
        close(s);

        // Check status
        if (ifm.ifm_status & IFM_AVALID) {
            if (ifm.ifm_status & IFM_ACTIVE)
                return true;   // cable plugged, link negotiated
        }
        return false;
    }

    std::vector<std::string> dnsForService(const std::string& serviceID) const {
        SCDynamicStoreRef store = nullptr;
        CFDictionaryRef dnsInfo = nullptr;
        CFStringRef dnsKey = nullptr;
        CFArrayRef servers = nullptr;
        std::vector<std::string> result;
        
        try {
            if (serviceID.empty())
                throw std::runtime_error("service id is empty");
            if (!(store = SCDynamicStoreCreate(nullptr, CFSTR("dns-reader"), nullptr, nullptr)))
                throw std::runtime_error("SCDynamicStoreCreate returned nullptr");

            CFStringRef dnsKey = CFStringCreateWithFormat(
                nullptr, nullptr,
                CFSTR("State:/Network/Service/%@/DNS"),
                CFStringCreateWithCString(nullptr, serviceID.c_str(), kCFStringEncodingUTF8)
            );

            if (!(dnsInfo = (CFDictionaryRef)SCDynamicStoreCopyValue(store, dnsKey)))
                throw std::runtime_error("dnsInfo returned nullptr");

            if (!(servers = (CFArrayRef)CFDictionaryGetValue(dnsInfo, CFSTR("ServerAddresses"))))
                throw std::runtime_error("servers returned nullptr");

            CFIndex count = CFArrayGetCount(servers);
            for (CFIndex i = 0; i < count; i++) {
                CFStringRef server = (CFStringRef)CFArrayGetValueAtIndex(servers, i);
                result.push_back(getStringFromRef(server));
            }
        }
        catch (const std::exception& e) {
            if ((std::string(e.what()) != "dnsInfo returned nullptr") && (std::string(e.what()) != "service id is empty"))
                std::cout << "DNSForService error: " << e.what() << std::endl;
        }

        if (dnsInfo) CFRelease(dnsInfo);
        if (store) CFRelease(store);
        if (dnsKey) CFRelease(dnsKey);
        return result;
    }

    void printFlags(unsigned int flags) const
    {
        struct { unsigned int flag; const char* name; } list[] = {
            {IFF_UP, "UP"},
            {IFF_BROADCAST, "BROADCAST"},
            {IFF_DEBUG, "DEBUG"},
            {IFF_LOOPBACK, "LOOPBACK"},
            {IFF_POINTOPOINT, "POINTOPOINT"},
            {IFF_NOTRAILERS, "NOTRAILERS"},
            {IFF_RUNNING, "RUNNING"},
            {IFF_NOARP, "NOARP"},
            {IFF_PROMISC, "PROMISC"},
            {IFF_ALLMULTI, "ALLMULTI"},
            {IFF_SIMPLEX, "SIMPLEX"},
            {IFF_LINK0, "LINK0"},
            {IFF_LINK1, "LINK1"},
            {IFF_LINK2, "LINK2"},
            {IFF_MULTICAST, "MULTICAST"},
        };

        for (auto& f : list) {
            if (flags & f.flag)
                std::cout << f.name << " ";
        }
    }

    void oldSchoolInterfaces() const
    {
        struct ifaddrs *ifaddr;
        int family, s;
        char host[NI_MAXHOST];

        if (getifaddrs(&ifaddr) == -1) {
            printf("Error: getifaddrs failed - %s\n", strerror(errno));
            return;
        }

        for (struct ifaddrs *ifa = ifaddr; ifa != nullptr; ifa = ifa->ifa_next) {
            if (ifa->ifa_addr == nullptr)
                continue;

            family = ifa->ifa_addr->sa_family;

            if (family == AF_INET ) {
                std::string address = inet_ntoa(((struct sockaddr_in *)ifa->ifa_addr)->sin_addr);
                std::cout << "address: " << address <<std::endl;
                std::cout << "name: " << ifa->ifa_name << std::endl;
                std::cout << "data: " << ifa->ifa_data << std::endl;
                std::cout << "flags: " << ifa->ifa_flags << std::endl;
                printInterfaceFlags(ifa->ifa_flags);
            } 
        }
        freeifaddrs(ifaddr);
    }

    void printInterfaceFlags(unsigned int flags) const {
        if (flags & IFF_UP)           std::cout << "UP ";
        if (flags & IFF_RUNNING)      std::cout << "RUNNING ";
        if (flags & IFF_LOOPBACK)     std::cout << "LOOPBACK ";
        if (flags & IFF_BROADCAST)    std::cout << "BROADCAST ";
        if (flags & IFF_POINTOPOINT)  std::cout << "P2P ";
        if (flags & IFF_MULTICAST)    std::cout << "MULTICAST ";
        if (flags & IFF_PROMISC)      std::cout << "PROMISC ";
        std::cout << std::endl;
    }

};

}

#endif // MACNETUTIL_HPP
