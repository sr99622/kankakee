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

#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>


namespace kankakee
{

class Broadcaster
{
public:
    struct sockaddr_in broadcast_address = {};
    std::string if_addr;
    std::string mult_addr;
    int port;
    SOCKET broadcast_socket = INVALID_SOCKET;
    std::function<void(const std::string&)> errorCallback = nullptr;

    ~Broadcaster() {
        if (broadcast_socket != INVALID_SOCKET) closesocket(broadcast_socket);
        WSACleanup();
    }    
 
    Broadcaster(const std::string& if_addr, const std::string& mult_addr, int port) : 
            if_addr(if_addr), mult_addr(mult_addr), port(port) {

        WSADATA wsaData;
        WSAStartup(MAKEWORD(2,2), &wsaData);

        int timeout_ms = 500;
        char loopch = 0;

        broadcast_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (broadcast_socket == INVALID_SOCKET)
                error("socket error", WSAGetLastError());

        sockaddr_in local_addr{};
        local_addr.sin_family = AF_INET;
        local_addr.sin_port = htons(0);
        local_addr.sin_addr.s_addr = inet_addr(if_addr.c_str());

        if ( bind (
            broadcast_socket,
            reinterpret_cast<sockaddr*>(&local_addr),
            sizeof(local_addr)
        ) == SOCKET_ERROR ) error("bind local interface error", WSAGetLastError());

        DWORD localInterface = inet_addr(if_addr.c_str());

        if ( setsockopt (
            broadcast_socket,
            IPPROTO_IP,
            IP_MULTICAST_IF,
            reinterpret_cast<const char *>(&localInterface),
            sizeof(localInterface)
        ) == SOCKET_ERROR ) error("IP_MULTICAST_IF error", WSAGetLastError());
        
        if ( setsockopt (
            broadcast_socket, 
            SOL_SOCKET, 
            SO_RCVTIMEO, 
            reinterpret_cast<const char *>(&timeout_ms), 
            sizeof(timeout_ms)
        ) == SOCKET_ERROR ) error("SO_RECVTIMEO error", WSAGetLastError());

        if ( setsockopt (
            broadcast_socket, 
            IPPROTO_IP, 
            IP_MULTICAST_LOOP, 
            reinterpret_cast<const char *>(&loopch), 
            sizeof(loopch)
        ) == SOCKET_ERROR ) error("IP_MULTICAST_LOOP error", WSAGetLastError());

        broadcast_address.sin_family = AF_INET;
        broadcast_address.sin_port = htons(port);
        broadcast_address.sin_addr.s_addr = inet_addr(mult_addr.c_str());
    }

    void send(const std::string& msg) {
        if ( sendto (
            broadcast_socket, 
            msg.c_str(), 
            msg.length(), 
            0, 
            reinterpret_cast<struct sockaddr*>(&broadcast_address), 
            sizeof(broadcast_address)
        ) < 0 ) error("broadcast send error", WSAGetLastError());
    }

    std::vector<std::string> recv() {
        std::vector<std::string> output;
        int address_size = sizeof(broadcast_address);
        while (true) {
            char buf[8192] = {0};
            int len = recvfrom(broadcast_socket, buf, sizeof(buf), 0, (struct sockaddr*) &broadcast_address, &address_size);
            if (len > 0) {
                output.push_back(buf);
            } else {
                if (len < 0) {
                    int code = WSAGetLastError();
                    if (code != WSAETIMEDOUT)
                        error("broadcaster recv error", code);
                }
                break;
            }
        }
        return output;
    }

    void enableLoopback(bool arg) {
        int loopback = arg ? 1 : 0;
        if ( setsockopt (
            broadcast_socket, 
            IPPROTO_IP, 
            IP_MULTICAST_LOOP, 
            (char *)&loopback, 
            sizeof(loopback)
        ) < 0 ) error("broadcast IP_MULTICAST_LOOP error: ", WSAGetLastError());
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
