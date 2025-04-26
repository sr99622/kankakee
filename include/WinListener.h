/********************************************************************
* kankakee/include/WinListener.h
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

#ifndef WINLISTENER_H
#define WINLISTENER_H

#include <stdlib.h> 
#include <string.h> 
#include <functional>
#include <exception>
#include <iostream>
#include <sstream>
#include <thread>

#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>

#define PORT 8080 
#define BUF_SIZE 1024
#define MULTICAST_ADDR "239.255.255.247"

namespace kankakee

{

class Listener
{
public:
	int sock = -1;
	bool running = false;
	struct sockaddr_in servaddr;
	std::vector<std::string> ip_addrs;
	std::function<void(const std::string&)> errorCallback = nullptr;
	std::function<void(const std::string&)> listenCallback = nullptr;

	~Listener() { if (sock > 0) close(sock); }
	Listener(const std::vector<std::string>& ip_addrs) : ip_addrs(ip_addrs) { }

	void initialize() {
		if ((sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)) < 0)
			error("creation error", WSAGetLastError());

		int reuse = 1;
		if (setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, (char*)&reuse, sizeof(reuse)) < 0)
			error("reuse error", WSAGetLastError());

        u_long flags = 1;
        if (ioctlsocket(sock, FIONBIO, &flags) == SOCKET_ERROR) 
            error("server ioctl exception", WSAGetLastError());

		memset(&servaddr, 0, sizeof(servaddr));
		servaddr.sin_family = AF_INET;
		servaddr.sin_addr.s_addr = INADDR_ANY; 
		servaddr.sin_port = htons(PORT); 
		
		if (bind(sock, (const struct sockaddr*)&servaddr, sizeof(servaddr)) < 0)
			error("bind error", WSAGetLastError()); 

		for (int i = 0; i < ip_addrs.size(); i++) {
			struct ip_mreq group;
			memset(&group, 0, sizeof(group));
			group.imr_multiaddr.s_addr = inet_addr(MULTICAST_ADDR);
			group.imr_interface.s_addr = inet_addr(ip_addrs[i].c_str());
			if (setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, (char*)&group, sizeof(group)) < 0)
				error("add multicast membership error", WSAGetLastError());
		}
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
		str << "Listener exception: " << ex.what();
		if (errorCallback) errorCallback(str.str());
		else std::cout << str.str() << std::endl;
	}

	void start() {
		initialize();
		running = true;
		std::thread thread([&]() { listen(); });
		thread.detach();
	}

	void stop() {
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
			error("listener socket close time out error", ETIMEDOUT);
	}

	void listen() {
		while (running) {
			try {
				struct sockaddr_in addr;
				socklen_t len = sizeof(addr);
				memset(&addr, 0, sizeof(addr));
				char buffer[BUF_SIZE] = { 0 };
				if (recvfrom(sock, buffer, 1024, 0, (struct sockaddr *) &addr, &len) < 0) {
					if (WSAGetLastError() == WSAEWOULDBLOCK) {
						std::this_thread::sleep_for(std::chrono::milliseconds(100));
						continue;
					}
					else {
						error("recvfrom error", WSAGetLastError());
					}
				}

				if (listenCallback) listenCallback(buffer);
			}
			catch (const std::exception& ex) {
				alert(ex);
			}
		}

		try {
			if (sock > 0) {
				if (closesocket(sock) < 0)
					error("close error", WSAGetLastError());
				sock = -1;
			}
		}
		catch (const std::exception& ex) {
			alert(ex);
		}
	}
};

}

#endif // WINLISTENER_H
