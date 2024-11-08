/********************************************************************
* kankakee/include/WinServer.h
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

#ifndef WINSERVER_H
#define WINSERVER_H

#include <cstring>
#include <iostream>
#include <sstream>
#include <thread>
#include <vector>
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

class Server
{
public:
    WSAData wsaData = { 0 };
    SOCKET sock = INVALID_SOCKET;
    std::string ip;
    int port;

    bool enabled = true;
    bool running = false;
    
    std::function<const std::string(const std::string&)> serverCallback = nullptr;
    std::function<void(const std::string&)> errorCallback = nullptr;

    ~Server() {
        if (sock != INVALID_SOCKET) {
            if (closesocket(sock) == SOCKET_ERROR) {
                std::stringstream str;
                str << "server close socket exception: " << errorToString(WSAGetLastError());
                if (errorCallback) errorCallback(str.str());
                else std::cout << str.str() << std::endl;
            }
        } 
        if (wsaData.wVersion) WSACleanup();
    }

    Server(const std::string& ip, int port) : ip(ip), port(port) { 
        int result = WSAStartup(MAKEWORD(2, 2), &wsaData);
        if (result != NO_ERROR) {
            memset(&wsaData, 0, sizeof(wsaData));
            error("server wsa startup exception", result);
        }
    }

    void initialize() {
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) == INVALID_SOCKET)
            error("server socket exception", WSAGetLastError());

        BOOL opt = TRUE;
        if ((setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, (char *) &opt, sizeof(opt))) == SOCKET_ERROR)
            error("server setsockopt exception", WSAGetLastError());

        u_long flags = 1;
        if (ioctlsocket(sock, FIONBIO, &flags) == SOCKET_ERROR) 
            error("server ioctl exception", WSAGetLastError());

        struct sockaddr_in addr_in;
        addr_in.sin_family = AF_INET;
        addr_in.sin_port = htons(port);
        if (ip.length())
            addr_in.sin_addr.s_addr = inet_addr(ip.c_str());
        else
            addr_in.sin_addr.s_addr = INADDR_ANY;

        if (bind(sock, (struct sockaddr*)&addr_in, sizeof(addr_in)) == SOCKET_ERROR)
            error("server bind exception", WSAGetLastError());
        
        if (listen(sock, 5) == SOCKET_ERROR)
            error("server listen exception", WSAGetLastError());
    }

    void start() {
        initialize();
        running = true;
        enabled = true;
        std::thread thread([&]() { receive(); });
        thread.detach();
    }

    void stop() {
        enabled = false;
        while (running)
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
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

    void alert(const std::exception& ex) {
        std::stringstream str;
        str << "Server exception: " << ex.what();
        if (errorCallback) errorCallback(str.str());
        else std::cout << str.str() << std::endl;
    }

    bool endsWith(const std::string &arg, const std::string &delimiter) {
        bool result = false;
        if (arg.size() >= delimiter.size())
            if (!arg.compare(arg.size() - delimiter.size(), delimiter.size(), delimiter))
                result = true;
        return result;
    }

    void receive() {
        while (enabled) {
            SOCKET client = INVALID_SOCKET;
            try {
                struct sockaddr addr;
                int len = sizeof(addr);
                client = accept(sock, &addr, &len);

                if (client == INVALID_SOCKET) {
                    int err = WSAGetLastError();
                    if (err == WSAEWOULDBLOCK) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(100));
                        continue;
                    }
                    else {
                        error("accept exception", err);
                    }
                }

                u_long flags = 1;
                if (ioctlsocket(client, FIONBIO, &flags) == SOCKET_ERROR) 
                    error("ioctl exception", WSAGetLastError());

                struct sockaddr_in *addr_in = (struct sockaddr_in *)&addr;
                char ip[INET_ADDRSTRLEN] = {0};
                if (!inet_ntop(AF_INET, &(addr_in->sin_addr), ip, INET_ADDRSTRLEN))
                    error("inet_ntop exception", WSAGetLastError());

                char buffer[1024] = { 0 };
                int result = 0;
                std::stringstream input;

                do {
                    memset(buffer, 0, sizeof(buffer));
                    result = recv(client, buffer, sizeof(buffer), 0);

                    if (result > 0)  {
                        input << std::string(buffer).substr(0, 1024);  
                        if (endsWith(input.str(), "\r\n"))
                            break;
                    }
                    else if (result < 0) {
                        int last_error = WSAGetLastError();
                        if (last_error == WSAEWOULDBLOCK) {
                            fd_set fds;
                            FD_ZERO(&fds);
                            FD_SET(client, &fds);
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

                std::string client_request = input.str();
                client_request = client_request.substr(0, client_request.length()-2);

                std::string response = serverCallback(client_request.c_str());
                if (send(client, response.c_str(), response.length(), 0) == SOCKET_ERROR)
                    error("send exception", WSAGetLastError());

                if (closesocket(client) == SOCKET_ERROR)
                    error("client close socket exception", WSAGetLastError());
                client = INVALID_SOCKET;

            }
            catch (const std::exception& ex) {
                alert(ex);
            }

            try {
                if (client != INVALID_SOCKET) {
                    if (closesocket(client) == SOCKET_ERROR)
                        error("client fallback close socket exception", WSAGetLastError());
                }
            }
            catch (const std::exception& ex) {
                alert(ex);
            }
        }

        try {
            if (sock != INVALID_SOCKET) {
                if (closesocket(sock) == SOCKET_ERROR)
                    error("socket close exception", WSAGetLastError());
            }
        }
        catch (const std::exception& ex) {
            alert(ex);
        }

        sock = INVALID_SOCKET;
        running = false;
    }
};

}

#endif // WINSERVER_H