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
    std::vector<uint8_t> request;
    std::function<void(const std::string&)> errorCallback = nullptr;
    std::function<void(const std::vector<uint8_t>&)> clientCallback = nullptr;
    int timeout = 5;

    ~Client() {  }

    Client(const std::string& ip, int port) {
        setEndpoint(ip, port);
    }

    void setEndpoint(const std::string& ip, int port)
    {
        /*
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
        */

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

    void transmit(const std::vector<uint8_t>& request) {
        Client client = *this;
        client.request = request;
        std::thread thread([](Client c) { c.run(); }, client);
        thread.detach();
    }

    int pollWait(int sock, short event) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(sock, &fds);
        TIMEVAL poll_timeout = {timeout, 0};
        int result = -1;
        if (event == POLLOUT)
            result = select(0, nullptr, &fds, nullptr, &poll_timeout);
        else if (event == POLLIN)
            result = select(0, &fds, nullptr, nullptr, &poll_timeout);
        if (result <= 0)  {
            if (result == 0)
                error("client write poll_timeout", WSAGetLastError());
            else
                error("client write exception", WSAGetLastError());
        }
        return result;
    }

    void run() {
        std::vector<uint8_t> received;
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
            if (result < 0) {
                int last_error = WSAGetLastError();
                if (last_error == WSAEWOULDBLOCK) {
                    result = pollWait(sock, POLLOUT);
                }
                else {
                    error("client connect exception", last_error);
                }
            }

            int accum = 0;
            do {
                result = send(sock, reinterpret_cast<char*>(request.data() + accum), request.size() - accum, 0);
                if (result > 0) {
                    accum += result;
                }
                else if (result < 0) {
                    int last_error = WSAGetLastError();
                    if (last_error == WSAEWOULDBLOCK) {
                        result = pollWait(sock, POLLOUT);
                    }
                    else {
                        error("client send exception", WSAGetLastError());
                    }
                }
            } while (result > 0);

            int BUFFER_SIZE = 1024 * 1024;
            std::vector<uint8_t> buffer(BUFFER_SIZE);
            result = 0;
            do {
                result = recv(sock, reinterpret_cast<char*>(buffer.data()), buffer.size(), 0);

                if (result > 0)  {
                    received.insert(received.end(), buffer.data(), buffer.data() + result);
                }
                else if (result < 0) {
                    int last_error = WSAGetLastError();
                    if (last_error == WSAEWOULDBLOCK) {
                        result = pollWait(sock, POLLIN);
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
        if (clientCallback) clientCallback(received);

    }
};

}

#endif // WINCLIENT_H