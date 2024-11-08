/********************************************************************
* kankakee/include/WinClient.h
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

#ifndef WINCLIENT_H
#define WINCLIENT_H

#include <cstring>
#include <iostream>
#include <sstream>
#include <thread>
#include <vector>
#include <algorithm>
#include <exception>
#include <functional>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef UNICODE
#define UNICODE
#endif

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>

namespace kankakee
{

class Client
{
public:
    SOCKET sock = INVALID_SOCKET;
    sockaddr_in addr;
    std::string msg;
    std::function<void(const std::string&)> errorCallback = nullptr;
    std::function<void(const std::string&)> clientCallback = nullptr;

    ~Client() {  }

    Client(const std::string& ip_addr) {
        setEndpoint(ip_addr);
    }

    void setEndpoint(const std::string& ip_addr)
    {
        std::string arg = ip_addr;
        std::replace( arg.begin(), arg.end(), ':', ' ');
        auto iss = std::istringstream{arg};
        auto str = std::string{};

        std::string ip;
        int port;
        int count = 0;
        while (iss >> str) {
            if (count == 0) {
                ip = str;
            }
            if (count == 1) {
                try {
                    port = std::stoi(str);
                }
                catch (const std::exception& ex) {
                    std::stringstream str;
                    str << "client create invalid port : " << ex.what();
                    throw std::runtime_error(str.str());
                }
            }
            count++;
        }   

        struct in_addr tmp;
        int result = inet_pton(AF_INET, ip.c_str(), &tmp);
        if (result <= 0) {
            if (result == 0) 
                error("client invalid ip address", WSA_INVALID_PARAMETER);
            else
                error("client ip address conversion exception", WSAGetLastError());
        }

        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        addr.sin_addr.s_addr = tmp.s_addr;
    }

    const std::string errorToString(int err) {
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

    void transmit(const std::string& msg) {
        Client client = *this;
        client.msg = msg;
        std::thread thread([](Client c) { c.run(); }, client);
        thread.detach();
    }

    void run() {
        std::stringstream output;
        WSADATA wsaData = { 0 };

        try {

            int result = WSAStartup(MAKEWORD(2, 2), &wsaData);
            if (result != NO_ERROR) {
                memset(&wsaData, 0, sizeof(wsaData));
                error("client wsa setup exception", result);
            }

            sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
            if (sock == INVALID_SOCKET)
                error("client socket creation exception", WSAGetLastError());

            u_long flags = 1;
            if (ioctlsocket(sock, FIONBIO, &flags) < 0) 
                error("client socket ioctl error", WSAGetLastError());
            
            result = connect(sock, (struct sockaddr*)&addr, sizeof(addr));
            if (result == SOCKET_ERROR) {
                int last_error = WSAGetLastError();
                if (last_error == WSAEWOULDBLOCK) {
                    fd_set fds;
                    FD_ZERO(&fds);
                    FD_SET(sock, &fds);
                    TIMEVAL timeout = {3, 0};
                    result = select(0, nullptr, &fds, nullptr, &timeout);
                    if (result <= 0)  {
                        if (result == 0)
                            throw std::runtime_error("client connect timeout");
                        else
                            error("client accept exception", WSAGetLastError());
                    }
                }
                else {
                    error("client connect exception", last_error);
                }
            }

            result = send(sock, msg.c_str(), msg.length(), 0);
            if (result == SOCKET_ERROR) {
                error("client send exception", WSAGetLastError());
            }
            else if (result < msg.length()) {
                throw std::runtime_error("client failed to send complete message");
            }

            char buffer[1024] = { 0 };
            result = 0;
            do {
                memset(buffer, 0, sizeof(buffer));
                result = recv(sock, buffer, sizeof(buffer), 0);

                if (result > 0)  {
                    output << std::string(buffer).substr(0, 1024);                
                }
                else if (result < 0) {
                    int last_error = WSAGetLastError();
                    if (last_error == WSAEWOULDBLOCK) {
                        fd_set fds;
                        FD_ZERO(&fds);
                        FD_SET(sock, &fds);
                        TIMEVAL timeout = {3, 0};
                        result = select(0, &fds, nullptr, nullptr, &timeout);
                        if (result <= 0)  {
                            if (result == 0)
                                throw std::runtime_error("recv timeout occurred");
                            else
                                error("client recv select exception", WSAGetLastError());
                        }
                    }
                    else {
                        error("client recv exception", last_error);
                    }
                }

            } while (result > 0);            
        }
        catch (const std::exception& ex) {
            std::stringstream str;
            str << "client receive exception: " << ex.what();
            if (errorCallback) errorCallback(str.str());
            else std::cout << str.str() << std::endl;
        }

        try {
            if (sock != INVALID_SOCKET) {
                if (closesocket(sock) == SOCKET_ERROR)
                    error("client close socket excecption", WSAGetLastError());
            }
        }
        catch (const std::exception& ex) {
            std::stringstream str;
            str << "client close socket exception: " << ex.what();
            if (errorCallback) errorCallback(str.str());
            else std::cout << str.str() << std::endl;
        }

        if (wsaData.wVersion) WSACleanup();
        if (clientCallback) clientCallback(output.str());
    }
};

}

#endif // WINCLIENT_H