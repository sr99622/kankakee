/********************************************************************
* kankakee/include/Server.h
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

#ifndef SERVER_H
#define SERVER_H

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

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <fcntl.h>
#include <errno.h>

namespace kankakee
{

class Server
{
public:
    int sock = -1;
    std::string ip;
    int port;
    bool running = false;

    std::function<const std::string(const std::string&)> serverCallback = nullptr;
    std::function<void(const std::string&)> errorCallback = nullptr;

    ~Server() { if (sock > 0) close(sock); }
    Server(const std::string& ip, int port) : ip(ip), port(port) { }

    void initialize() {
        // initialize errors are intended to bubble up to python
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0)
            error("server socket create exception", errno);

        int opt = 1;
        if (setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)))
            error("server setsockopt SO_REUSEADDR exception", errno);

        unsigned long flags = 1;
        if (ioctl(sock, FIONBIO, &flags) < 0) 
            error("server ioctl exception", errno);

        struct sockaddr_in addr_in;
        addr_in.sin_family = AF_INET;
        addr_in.sin_port = htons(port);
        if (ip.length())
            addr_in.sin_addr.s_addr = inet_addr(ip.c_str());
        else
            addr_in.sin_addr.s_addr = INADDR_ANY;

        if (bind(sock, (struct sockaddr*)&addr_in, sizeof(addr_in)) < 0)
            error("server bind exception", errno);

        if (listen(sock, 5) < 0)
            error("server listen exception", errno);
    }

    void start()
    {
        initialize();
        running = true;
        std::thread thread([&]() { receive(); });
        thread.detach();
    }

    void stop()
    {
        running = false;

		auto start = std::chrono::steady_clock::now();
		bool success = false;

		while (true) {
			std::this_thread::sleep_for(std::chrono::milliseconds(500));
			auto end = std::chrono::steady_clock::now();
			std::chrono::duration<double> elapsed_seconds = end - start;

			if (sock < 0) {
				success = true;
				break;
			}
			if (elapsed_seconds.count() > 5) {
				success = false;
				break;
			}
		}

		if (!success)
			error("server socket close time out error", ETIMEDOUT);
    
    }

    void error(const std::string& msg, int err) {
        std::stringstream str;
        str << msg << " : " << strerror(err);
        throw std::runtime_error(str.str());
    }

    void alert(const std::exception& ex) {
        std::stringstream str;
        str << "Server exception: " << ex.what();
        if (errorCallback) errorCallback(str.str());
        else std::cout << str.str() << std::endl;
    }

    bool endsWith(const std::string &arg, const std::string &delimiter)
    {
        bool result = false;
        if (arg.size() >= delimiter.size())
            if (!arg.compare(arg.size() - delimiter.size(), delimiter.size(), delimiter))
                result = true;
        return result;
    }

    const std::string getClientRequest(int client)
    {
        char buffer[1024] = { 0 };
        int result = 0;
        std::stringstream input;

        do {
            memset(buffer, 0, sizeof(buffer));
            result = recv(client, buffer, sizeof(buffer), 0);

            if (result > 0) {
                input << std::string(buffer).substr(0, 1024);
                if (endsWith(input.str(), "\r\n"))
                    break;
            }
            else if (result < 0) {
                if (errno == EWOULDBLOCK) {
                    fd_set fds;
                    FD_ZERO(&fds);
                    FD_SET(client, &fds);
                    struct timeval timeout = {3, 0};
                    result = select(client+1, &fds, nullptr, nullptr, &timeout);
                    if (result <= 0)  {
                        if (result == 0)
                            throw std::runtime_error("recv timeout occurred");
                        else
                            error("client recv select exception", errno);
                    }
                }
                else {
                    error("client recv exception", errno);
                }
            }
        } while (result > 0);

        return input.str();
    }

    void receive() {
        while (running) {
            int client = -1;
            try {
                struct sockaddr addr;
                socklen_t len = sizeof(addr);
                client = accept(sock, &addr, &len);

                if (client < 0) {
                    if (errno == EWOULDBLOCK || errno == EAGAIN) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(100));
                        continue;
                    }
                    else {
                        error("accept exception", errno);
                    }
                }

                unsigned long flags = 1;
                if (ioctl(client, FIONBIO, &flags) < 0) 
                    error("ioctl exception", errno);

                struct sockaddr_in *addr_in = (struct sockaddr_in *)&addr;
                char ip[INET_ADDRSTRLEN] = {0};
                if (!inet_ntop(AF_INET, &(addr_in->sin_addr), ip, INET_ADDRSTRLEN))
                    error("inet_ntop exception", errno);

                std::string client_request = getClientRequest(client);
                client_request = client_request.substr(0, client_request.length()-2);

                std::string response = serverCallback(client_request.c_str());
                if (send(client, response.c_str(), response.length(), 0) < 0)
                    error("send exception", errno);
        
                if (close(client) < 0)
                    error("client close exception", errno);
                client = -1;

            }
            catch (const std::exception& ex) {
                alert(ex);
            }

            try {
                if (client > 0) {
                    if (close(client) < 0)
                        error("client fallback close exception", errno);
                }
            }
            catch(const std::exception& ex) {
                alert(ex);
            }
        }

        try {
            if (sock > 0) {
                if (close(sock) < 0)
                    error("socket close exception", errno);
                sock = -1;
            }
        }
        catch (const std::exception& ex) {
            alert(ex);
        }
    }
};

}

#endif // SERVER_H