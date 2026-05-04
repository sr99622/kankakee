/********************************************************************
* kankakee/include/Broadcaster.h
*
* Copyright (c) 2024  Stephen Rhodes
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*
*********************************************************************/

#ifndef BROADCASTER_H
#define BROADCASTER_H

#include <stdlib.h> 
#include <string.h> 
#include <functional>
#include <exception>
#include <sstream>
#include <iostream>

#ifdef _WIN32
    #ifndef UNICODE
    #define UNICODE
    #endif
    #define WIN32_LEAN_AND_MEAN
    #include <winsock2.h>
    #include <ws2tcpip.h>
#else
    #include <unistd.h> 
    #include <sys/types.h> 
    #include <sys/socket.h> 
    #include <arpa/inet.h> 
    #include <netinet/in.h>
#endif

namespace kankakee

{

class Broadcaster
{
public:
    struct sockaddr_in broadcast_address;
    std::string if_addr;
    std::string mult_addr;
    int port;
    int sock = -1;
    std::function<void(const std::string&)> errorCallback = nullptr;

    ~Broadcaster() {
        if (sock > -1) closesocket(sock);
    }    
 
    Broadcaster(const std::string& if_addr, const std::string& mult_addr, int port) : 
            if_addr(if_addr), mult_addr(mult_addr), port(port) {

        if ((sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)) < 0)
            error("broadcast socket creation error", WSAGetLastError());

        struct in_addr interface;
        memset(&interface, 0, sizeof(interface));
        interface.s_addr = inet_addr(if_addr.c_str());
        if (setsockopt(sock, IPPROTO_IP, IP_MULTICAST_IF, (const char *)&interface, sizeof(interface)) < 0)
            error("broadcast IP_MULTICAST_IF error: ", WSAGetLastError());

            int timeout_ms = 500;
            if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                        reinterpret_cast<const char*>(&timeout_ms),
                        sizeof(timeout_ms)) < 0)
                error("broadcast SO_RECVTIMEO error: ", WSAGetLastError());

        char loopback = 0;
        if (setsockopt(sock, IPPROTO_IP, IP_MULTICAST_LOOP, (char *)&loopback, sizeof(loopback)) < 0)
            error("broadcast IP_MULTICAST_LOOP error: ", WSAGetLastError());

        memset(&broadcast_address, 0, sizeof(broadcast_address)); 
        broadcast_address.sin_family = AF_INET; 
        broadcast_address.sin_port = htons(port); 
        broadcast_address.sin_addr.s_addr = inet_addr(mult_addr.c_str());
    }

    void send(const std::string& msg) {
        try {
            if (sendto(sock, msg.c_str(), msg.length(), 0, (const struct sockaddr *) &broadcast_address, sizeof(broadcast_address)) < 0)
                error("broadcast send error", WSAGetLastError());
        }
        catch (const std::exception& ex) {
            alert(ex);
        }
    }

    std::vector<std::string> recv() {
        std::vector<std::string> output;

        std::cout << "Waiting for broadcast messages..." << std::endl; 

        int address_size = sizeof(broadcast_address);
        
        try {
            while (true) {
                char buf[8192] = {0};
                int result = recvfrom(sock, buf, sizeof(buf), 0, (struct sockaddr*) &broadcast_address, &address_size);
                if (result > 0) {
                    std::cout << "Received broadcast message: " << buf << std::endl;
                    output.push_back(buf);
                }
                else {
                    if (result < 0) {
                        if (WSAGetLastError() != WSAEWOULDBLOCK)
                            error("broadcast recv error", WSAGetLastError());
                    }
                    break;
                }
            }
        }
        catch (const std::exception& ex) {
            alert(ex);
        }
        return output;
    }

    void enableLoopback(bool arg) {
        int loopback = arg ? 1 : 0;
        if (setsockopt(sock, IPPROTO_IP, IP_MULTICAST_LOOP, (char *)&loopback, sizeof(loopback)) < 0)
            error("broadcast IP_MULTICAST_LOOP error: ", WSAGetLastError());
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

    void alert(const std::exception& ex) {
        std::stringstream str;
        str << "Broadcast exception: " << ex.what();
        if (errorCallback) errorCallback(str.str());
            else std::cout << str.str() << std::endl;
    }
};

}

#endif // BROADCASTER_H
