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

#define PORT 8080 
#define MAXLINE 1024 

namespace kankakee

{

class Broadcaster
{
public:
	struct sockaddr_in servaddr;
	std::vector<std::string> if_addrs;
	std::vector<int> socks;
	std::function<void(const std::string&)> errorCallback = nullptr;

	~Broadcaster() { 
		for (int i = 0; i < socks.size(); i++) 
			if (socks[i] > -1) close(socks[i]);

		socks.clear();
		if_addrs.clear();
	}
	
	Broadcaster(const std::vector<std::string>& if_addrs) : if_addrs(if_addrs) {
		int sock = -1;
		int loopback = 0;
		memset(&servaddr, 0, sizeof(servaddr)); 
		servaddr.sin_family = AF_INET; 
		servaddr.sin_port = htons(PORT); 
		servaddr.sin_addr.s_addr = inet_addr("239.255.255.247");

		for (int i = 0; i < if_addrs.size(); i++) {
			struct in_addr interface;
			memset(&interface, 0, sizeof(interface));
			interface.s_addr = inet_addr(if_addrs[i].c_str());
			if ((sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)) < 0)
				error("broadcast socket creation error", errno);

			if (setsockopt(sock, IPPROTO_IP, IP_MULTICAST_LOOP, (char *)&loopback, sizeof(loopback)) < 0)
				error("IP_MULTICAST_LOOP error: ", errno);

			if (setsockopt(sock, IPPROTO_IP, IP_MULTICAST_IF, (const char *)&interface, sizeof(interface)) < 0)
				error("IP_MULTICAST_IF error: ", errno);
			
			socks.push_back(sock);
		}
	}

	void enableLoopback(bool arg) {
		for (int i = 0; i < socks.size(); i++) {
			int loopback = arg ? 1 : 0;
			if (setsockopt(socks[i], IPPROTO_IP, IP_MULTICAST_LOOP, (char *)&loopback, sizeof(loopback)) < 0)
				error("IP_MULTICAST_LOOP error: ", errno);
		}
	}

	void send(const std::string& msg) {
		for (int i = 0; i < socks.size(); i++) {
			try {
				if (sendto(socks[i], msg.c_str(), msg.length(), 0, (const struct sockaddr *) &servaddr, sizeof(servaddr)) < 0)
					error("send error", errno);
			}
			catch (const std::exception& ex) {
				alert(ex);
			}
		}
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
};

}

#endif // BROADCASTER_H
