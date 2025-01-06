/********************************************************************
* kankakee/include/Client.h
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

#ifndef CLIENT_H
#define CLIENT_H

#include <cstring>
#include <iostream>
#include <sstream>
#include <thread>
#include <vector>
#include <algorithm>
#include <exception>
#include <functional>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <poll.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <fcntl.h>
#include <errno.h>

namespace kankakee
{

class Client
{
public:
    int sock = -1;
    sockaddr_in addr;
    std::string msg;

    std::function<void(const std::string&)> errorCallback = nullptr;
    std::function<void(const std::string&)> clientCallback = nullptr;

    ~Client() {}
    Client(const std::string& ip_addr) {
        setEndpoint(ip_addr);
    }

    void setEndpoint(const std::string& ip_addr) {
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
                    str << "client set endpoint create invalid port : " << ex.what();
                    error(str.str(), 22);
                }
            }
            count++;
        }   

        struct in_addr tmp;
        if (!inet_pton(AF_INET, ip.c_str(), &tmp))
            error("client set endpoint create invalid ip address",  6);

        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        addr.sin_addr.s_addr = tmp.s_addr;
    }

    void error(const std::string& msg, int err) {
        std::stringstream str;
        str << msg << " : " << strerror(err);
        throw std::runtime_error(str.str());
    }

    void transmit(const std::string& msg) {
        Client client = *this;
        client.msg = msg;
        std::thread thread([](Client c) { c.run(); }, client);
        thread.detach();
    }

    int pollWait(int fd, short events) {
        struct pollfd pfd;
        pfd.fd = fd;
        pfd.events = events;

        int poll_result = poll(&pfd, 1, 5000);
        if (poll_result > 0) {
            if (pfd.revents & events) {
                int so_error;
                socklen_t len = sizeof(so_error);
                getsockopt(sock, SOL_SOCKET, SO_ERROR, &so_error, &len);
                if (so_error != 0)
                    error("client connect exception", so_error);
            }
        }
        else if (poll_result == 0) {
            error("client connection timed out", errno);
        }
        else {
            error("client poll error", errno);
        }
        return poll_result;
    }

    void run() {
        std::stringstream output;

        try {
            sock = socket(AF_INET, SOCK_STREAM, 0);
            
            int flags = 1;
            if (ioctl(sock, FIONBIO, &flags) < 0) 
                error("client socket ioctl error", errno);

            int result = 0;
            result = connect(sock, (struct sockaddr*)&addr, sizeof(addr));

            if (result < 0) {
                if (errno == EINPROGRESS) {
                    result = pollWait(sock, POLLOUT);
                }
            }

            if (send(sock, msg.c_str(), msg.length(), 0) < 0)
                error("client send exception", errno);

            char buffer[1024] = { 0 };
            result = 0;
            do {
                memset(buffer, 0, sizeof(buffer));
                result = recv(sock, buffer, sizeof(buffer), 0);

                if (result > 0) {
                    output << std::string(buffer).substr(0, 1024);
                }
                else if (result < 0) {
                    if (errno == EWOULDBLOCK || errno == EAGAIN) {
                        result = pollWait(sock, POLLIN);
                    }
                    else {
                        error("client read exception", errno);
                    }
                }
            } while (result > 0);
        }
        catch (const std::exception& ex) {
            std::stringstream str;
            str << "client receive exception: " << ex.what();
            if (errorCallback) errorCallback(str.str());
            else std::cout << str.str() << std::endl;
            return;
        }
        
        if (sock > -1) close(sock);
        if (clientCallback) clientCallback(output.str());
    }
};

}

#endif // CLIENT_H