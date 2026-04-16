#ifndef WINNETUTIL_HPP
#define WINNETUTIL_HPP

#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <sys/stat.h>

#include <ws2tcpip.h>
#include <winsock2.h>
#include <wincrypt.h>
#include <iphlpapi.h>
#include <fcntl.h>
#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "ws2_32.lib")

#include <stdint.h>
#include <errno.h>
#include <vector>
#include <map>
#include <sstream>
#include <iomanip>

//#include "wabash.hpp"

#define WORKING_BUFFER_SIZE 15000
#define MAX_TRIES 3

#define MALLOC(x) HeapAlloc(GetProcessHeap(), 0, (x))
#define FREE(x) HeapFree(GetProcessHeap(), 0, (x))

namespace kankakee
{

class NetUtil
{
public:
    WSAData wsaData = { 0 };

    NetUtil() {
        int result = NO_ERROR;
        if (result = WSAStartup(MAKEWORD(2, 2), &wsaData) != NO_ERROR) 
            error("server wsa startup exception", result);
    }

    ~NetUtil() {
        if (wsaData.wVersion) WSACleanup();
    }

    std::vector<Adapter> getAllAdapters() const {
        std::vector<Adapter> results;
        std::unordered_map<DWORD, std::unordered_map<std::string, std::string>> adapters = GetAllAdapters();


        DWORD dwRetVal = 0;

        unsigned int i = 0;

        // Set the flags to pass to GetAdaptersAddresses
        ULONG flags = GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_INCLUDE_GATEWAYS;

        LPVOID lpMsgBuf = NULL;

        PIP_ADAPTER_ADDRESSES pAddresses = NULL;
        ULONG outBufLen = 0;
        ULONG Iterations = 0;

        PIP_ADAPTER_ADDRESSES pCurrAddresses = NULL;
        PIP_ADAPTER_UNICAST_ADDRESS pUnicast = NULL;
        PIP_ADAPTER_ANYCAST_ADDRESS pAnycast = NULL;
        PIP_ADAPTER_MULTICAST_ADDRESS pMulticast = NULL;
        PIP_ADAPTER_GATEWAY_ADDRESS_LH pGateway = NULL;
        PIP_ADAPTER_DNS_SERVER_ADDRESS pDnServer = NULL;
        IP_ADAPTER_PREFIX *pPrefix = NULL;

        ULONG family = AF_INET;  //  [AF_INET, AF_INET6, AF_UNSPEC]

        // Allocate a 15 KB buffer to start with, if that's not enough, try max three times to allocate.
        outBufLen = WORKING_BUFFER_SIZE;
        do {
            pAddresses = (IP_ADAPTER_ADDRESSES *) MALLOC(outBufLen);
            if (pAddresses == NULL) {
                printf("Memory allocation failed for IP_ADAPTER_ADDRESSES struct\n");
                return results;
            }
            dwRetVal = GetAdaptersAddresses(family, flags, NULL, pAddresses, &outBufLen);
            if (dwRetVal == ERROR_BUFFER_OVERFLOW) {
                FREE(pAddresses);
                pAddresses = NULL;
            } 
            else {
                break;
            }
            Iterations++;
        } while ((dwRetVal == ERROR_BUFFER_OVERFLOW) && (Iterations < MAX_TRIES));

        if (dwRetVal == NO_ERROR) {
            // If successful, output some information from the data we received
            pCurrAddresses = pAddresses;
            while (pCurrAddresses) {
                Adapter adapter;
                //printf("\tLength of the IP_ADAPTER_ADDRESS struct: %ld\n", pCurrAddresses->Length);

                printf("\n\tIfIndex (IPv4 interface): %u\n", pCurrAddresses->IfIndex);
                printf("\tAdapter name: %s\n", pCurrAddresses->AdapterName);

                //adapter.name = pCurrAddresses->AdapterName;

                pUnicast = pCurrAddresses->FirstUnicastAddress;
                if (pUnicast) {
                    adapter.ip_address = getSockIPAddress(pUnicast->Address.lpSockaddr);
                }

                /*
                pMulticast = pCurrAddresses->FirstMulticastAddress;
                while (pMulticast) {
                    std::cout << "\tMulticast Address: " << getSockIPAddress(pMulticast->Address.lpSockaddr) << std::endl;
                    pMulticast = pMulticast->Next;
                }
                */

                pDnServer = pCurrAddresses->FirstDnsServerAddress;
                while (pDnServer) {
                    std::cout << "\tDNS Address: " << getSockIPAddress(pDnServer->Address.lpSockaddr) << std::endl;
                    adapter.dns.push_back(getSockIPAddress(pDnServer->Address.lpSockaddr));
                    pDnServer = pDnServer->Next;
                }

                pGateway = pCurrAddresses->FirstGatewayAddress;
                if (pGateway) {
                    adapter.gateway = getSockIPAddress(pGateway->Address.lpSockaddr);
                }

                pPrefix = pCurrAddresses->FirstPrefix;
                while (pPrefix) {
                    adapter.dns.push_back(getSockIPAddress(pPrefix->Address.lpSockaddr));
                    pPrefix = pPrefix->Next;
                }

                adapter.dhcp = false;
                if (pCurrAddresses->Flags & IP_ADAPTER_DHCP_ENABLED) {
                    adapter.dhcp = true;
                    std::cout << "\tDHCP Server Address: " << getSockIPAddress(pCurrAddresses->Dhcpv4Server.lpSockaddr) << std::endl;
                }
                else {
                    printf("\tDHCP not enabled\n");
                }

                std::wstring str1(pCurrAddresses->Description);
                adapter.description = std::string(str1.begin(), str1.end());
                std::wstring str2(pCurrAddresses->FriendlyName);
                adapter.name = std::string(str2.begin(), str2.end());
                //adapter.name = pCurrAddresses->FriendlyName;
                printf("\tDescription: %wS\n", pCurrAddresses->Description);
                printf("\tFriendly name: %wS\n", pCurrAddresses->FriendlyName);

                int length = (int)pCurrAddresses->PhysicalAddressLength;
                if (length != 0) {
                    std::stringstream str;
                    for (i = 0; i < length; i++) {
                        str << std::uppercase << std::hex << std::setw(2) << std::setfill('0') << (int) pCurrAddresses->PhysicalAddress[i];
                        if (i < length - 1) str << "-";
                    }
                    std::cout << "\tPhysical Address: " << str.str() << std::endl;
                    adapter.mac_address = str.str();
                }
                adapter.type = getTypeName(pCurrAddresses->IfType);
                std::cout << "\tIF Type: " << getTypeName(pCurrAddresses->IfType) << std::endl;
                adapter.up = std::string(getOperStatusName(pCurrAddresses->OperStatus)) == "Up";
                std::cout << "\tOperStatus: " << getOperStatusName(pCurrAddresses->OperStatus) << std::endl;
                adapter.priority = GetNetworkPriority(pCurrAddresses->IfIndex);
                std::cout << "\tNetwork Priority: " << GetNetworkPriority(pCurrAddresses->IfIndex) << std::endl;

                auto adapter1 = adapters.find(pCurrAddresses->IfIndex);
                if (adapter1 != adapters.end()) {
                    auto parameters = adapter1->second;
                    auto broadcast = parameters.find("Broadcast");
                    if (broadcast != parameters.end()) {
                        adapter.broadcast = broadcast->second;
                        std::cout << "\tBroadcast: " << broadcast->second << std::endl;
                    }
                    auto mask = parameters.find("SubnetMask");
                    if (mask != parameters.end()) {
                        adapter.netmask = mask->second;
                        std::cout << "\tSubnet Mask: " << mask->second << std::endl;
                    } 
                }

                results.push_back(adapter);
                pCurrAddresses = pCurrAddresses->Next;
            }
        } 
        else {
            printf("Call to GetAdaptersAddresses failed with error: %d\n", dwRetVal);
            if (dwRetVal == ERROR_NO_DATA) {
                printf("\tNo addresses were found for the requested parameters\n");
            }
            else {
                std::cout << errorToString(dwRetVal) << std::endl;
            }
        }

        if (pAddresses) {
            FREE(pAddresses);
        }
        return results;
    }

    std::vector<std::string> getIPAddress() const {
        std::vector<std::string> results;
        /* Declare and initialize variables */


        return results;
    }

    std::string errorToString(int err) const {
        wchar_t *lpwstr = nullptr;
        FormatMessage(
            FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
            nullptr, err, MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT), (LPWSTR)&lpwstr, 0, nullptr
        );
        int size = WideCharToMultiByte(CP_UTF8, 0, lpwstr, -1, NULL, 0, NULL, NULL);
        std::string output(size, 0);
        WideCharToMultiByte(CP_UTF8, 0, lpwstr, -1, &output[0], size, NULL, NULL);
        LocalFree(lpwstr);
        return output;
    }

    void error(const std::string& msg, int err) {
        std::stringstream str;
        str << msg << " : " << errorToString(err);
        throw std::runtime_error(str.str());
    }

    std::string getSockIPAddress(SOCKADDR* sockAddr) const {
        std::string result = "0.0.0.0";
        if (sockAddr) {
            if (sockAddr->sa_family == AF_INET) {
                sockaddr_in *ipv4 = (sockaddr_in*)sockAddr;
                result = inet_ntoa(ipv4->sin_addr);
            }
        }
        return result;
    }

    std::string getTypeName(DWORD IfType) const {
        switch (IfType) {
        case IF_TYPE_OTHER:
            return "Other";
            break;
        case IF_TYPE_ETHERNET_CSMACD:
            return "Ethernet";
            break;
        case IF_TYPE_ISO88025_TOKENRING:
            return "Token Ring";
            break;
        case IF_TYPE_PPP:
            return "PPP";
            break;
        case IF_TYPE_SOFTWARE_LOOPBACK:
            return "Loopback";
            break;
        case IF_TYPE_ATM:
            return "ATM";
            break;
        case IF_TYPE_IEEE80211:
            return "Wireless";
            break;
        case IF_TYPE_TUNNEL:
            return "Tunnerl";
            break;
        case IF_TYPE_IEEE1394:
            return "Firewire";
            break;
        default:
            return "Unknown";
        }
    }

    std::string getOperStatusName(IF_OPER_STATUS status) const {
        switch (status) {
        case IfOperStatusUp:
            return "Up";
            break;
        case IfOperStatusDown:
            return "Down";
            break;
        case IfOperStatusTesting:
            return "Testing";
            break;
        case IfOperStatusUnknown:
            return "Unknown";
            break;
        case IfOperStatusDormant:
            return "Dormant";
            break;
        case IfOperStatusNotPresent:
            return "Not Present";
            break;
        case IfOperStatusLowerLayerDown:
            return "Layer Down";
            break;
        default:
            return "Unknown";
        }
    }

    DWORD GetNetworkPriority(DWORD interfaceIndex) const {
        DWORD result = -1;
        MIB_IPINTERFACE_ROW row;
        InitializeIpInterfaceEntry(&row);
        row.Family = AF_INET;
        row.InterfaceIndex = interfaceIndex;

        DWORD dwRetVal = GetIpInterfaceEntry(&row);
        if (dwRetVal == NO_ERROR) {
            result = row.Metric;
        } else {
            printf("GetIpInterfaceEntry failed with error: %d\n", dwRetVal);
        }
        return result;
    }

    std::unordered_map<DWORD, std::unordered_map<std::string, std::string>> GetAllAdapters() const {
        std::unordered_map<DWORD, std::unordered_map<std::string, std::string>> results;
        PIP_ADAPTER_INFO pAdapterInfo;
        PIP_ADAPTER_INFO pAdapter = NULL;
        DWORD dwRetVal = 0;

        ULONG ulOutBufLen = sizeof (IP_ADAPTER_INFO);
        pAdapterInfo = (IP_ADAPTER_INFO *) malloc(sizeof (IP_ADAPTER_INFO));
        if (pAdapterInfo == NULL) {
            printf("Error allocating memory needed to call GetAdaptersinfo\n");
            return results;
        }

        if (GetAdaptersInfo(pAdapterInfo, &ulOutBufLen) == ERROR_BUFFER_OVERFLOW) {
            free(pAdapterInfo);
            pAdapterInfo = (IP_ADAPTER_INFO *) malloc(ulOutBufLen);
            if (pAdapterInfo == NULL) {
                printf("Error allocating memory needed to call GetAdaptersinfo\n");
                return results;
            }
        }

        if ((dwRetVal = GetAdaptersInfo(pAdapterInfo, &ulOutBufLen)) == NO_ERROR) {
            pAdapter = pAdapterInfo;
            while (pAdapter) {
                if (strcmp(pAdapter->IpAddressList.IpAddress.String, "0.0.0.0")) {
                    std::unordered_map<std::string, std::string> parameters;
                    parameters.insert(std::pair("IPAddress", pAdapter->IpAddressList.IpAddress.String));
                    parameters.insert(std::pair("Description", pAdapter->Description));
                    parameters.insert(std::pair("SubnetMask", pAdapter->IpAddressList.IpMask.String));
                    parameters.insert(std::pair("Gateway", pAdapter->GatewayList.IpAddress.String));
                    parameters.insert(std::pair("DHCP", (pAdapter->DhcpEnabled ? "TRUE" : "FALSE")));
                    std::string broadcast = getBroadcast(pAdapter->IpAddressList.IpAddress.String, pAdapter->IpAddressList.IpMask.String);
                    parameters.insert(std::pair("Broadcast", broadcast));
                    results.insert(std::pair(pAdapter->Index, parameters));
                }
                pAdapter = pAdapter->Next;
            }
        } 
        else {
            printf("GetAdaptersInfo failed with error: %d", dwRetVal);
        }
        if (pAdapterInfo)
            free(pAdapterInfo);

        return results;
    }

    std::string getBroadcast(const std::string& ipStr, const std::string& maskStr) const
    {
        std::string result;

        try {
            in_addr ip{}, mask{}, broadcast{};
            if (inet_pton(AF_INET, ipStr.c_str(), &ip) != 1)
                throw std::runtime_error("error converting ip address to in_addr");
            if (inet_pton(AF_INET, maskStr.c_str(), &mask) != 1)
                throw std::runtime_error("error converting mask address to in_addr");

            uint32_t ip_i    = ntohl(ip.s_addr);
            uint32_t mask_i  = ntohl(mask.s_addr);
            uint32_t bc_i    = (ip_i & mask_i) | (~mask_i);

            broadcast.s_addr = htonl(bc_i);

            char buf[INET_ADDRSTRLEN];
            if (!inet_ntop(AF_INET, &broadcast, buf, sizeof(buf)))
                throw std::runtime_error("error converting broadcast address to string");

            result = buf;
        }
        catch (const std::exception& e) {
            std::cout << "getBroadcast error: " << e.what() << std::endl;
        }
        return result;
    }    

    std::map<std::string, int> getActiveNetworkInterfaces() const {
        std::map<std::string, int> result;

        //printf("Primary Interface: %s\n", onvif_session->primary_network_interface);
        return result;
    }

};

}

#endif // WINNETUTIL_HPP


/*
    std::vector<std::string> getIPAddress() const {
        char buf[128] = { 0 };
        std::string result;
        std::vector<std::string> results;

        DWORD dwSize = 0;
        
        PMIB_IPADDRTABLE pIPAddrTable = (MIB_IPADDRTABLE *) malloc(sizeof(MIB_IPADDRTABLE));
        if (pIPAddrTable) {
            if (GetIpAddrTable(pIPAddrTable, &dwSize, 0) == ERROR_INSUFFICIENT_BUFFER) {
                free(pIPAddrTable);
                pIPAddrTable = (MIB_IPADDRTABLE *) malloc(dwSize);
            }
            if (pIPAddrTable == NULL) {
                return results;
            }
        }

        DWORD dwRetVal = 0;
        if ((dwRetVal = GetIpAddrTable(pIPAddrTable, &dwSize, 0)) != NO_ERROR) {
            return results;
        }

        IN_ADDR IPAddr;
        int p = 0;
        while (p < (int)pIPAddrTable->dwNumEntries) {
            IPAddr.S_un.S_addr = (u_long)pIPAddrTable->table[p].dwAddr;
            strcpy(buf, inet_ntoa(IPAddr));
            results.push_back(std::string(buf));
            p++;
        }

        if (pIPAddrTable) {
            free(pIPAddrTable);
            pIPAddrTable = nullptr;
        }

        return results;
    }

*/