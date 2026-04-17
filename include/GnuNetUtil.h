#ifndef GNUNETUTIL_HPP
#define GNUNETUTIL_HPP

#include <string.h>
#include <stdio.h>
#include <iostream>
#include <string>
#include <sstream>
#include <map>
#include <regex>
#include <algorithm>
#include <array>
#include <memory>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace kankakee
{

class NetUtil {
public:


    NetUtil() { }
    ~NetUtil() { }


    std::vector<Adapter> getAllAdapters() const {
        std::vector<Adapter> result;

        json data = json::parse(exec("ip -j addr"));
        json gdata = json::parse(exec("ip -j route show default"));
        auto metrics = ParseIpRouteOutput(exec("ip route"));

        for (auto& x : data.items()) {
            Adapter adapter;
            auto if_data = x.value();

            if (if_data.contains("ifname") && if_data["ifname"].is_string())
                adapter.name = if_data["ifname"].get<std::string>();

            if (if_data.contains("operstate") && if_data["operstate"].is_string())
                adapter.up = (if_data["operstate"].get<std::string>() == "UP");

            if (if_data.contains("address") && if_data["address"].is_string())
                adapter.mac_address = if_data["address"].get<std::string>();

            if (if_data.contains("addr_info") && if_data["addr_info"].is_array()) {
                for (auto& y : if_data["addr_info"].items()) {
                    auto addr = y.value();

                    if (addr.contains("family") && addr["family"].is_string() &&
                        addr["family"].get<std::string>() == "inet") {

                        if (addr.contains("local") && addr["local"].is_string())
                            adapter.ip_address = addr["local"].get<std::string>();

                        if (addr.contains("prefixlen") && addr["prefixlen"].is_number_integer())
                            adapter.netmask = prefixLengthToMask(addr["prefixlen"].get<int>());

                        if (addr.contains("broadcast") && addr["broadcast"].is_string())
                            adapter.broadcast = addr["broadcast"].get<std::string>();

                        adapter.dhcp = false;
                        if (addr.contains("dynamic") && addr["dynamic"].is_boolean())
                            adapter.dhcp = addr["dynamic"].get<bool>();
                    }
                }
            }

            for (auto& y : gdata.items()) {
                auto g_info = y.value();

                if (g_info.contains("dev") && g_info["dev"].is_string() &&
                    adapter.name == g_info["dev"].get<std::string>()) {
                    if (g_info.contains("gateway") && g_info["gateway"].is_string())
                        adapter.gateway = g_info["gateway"].get<std::string>();
                }
            }

            if (!adapter.name.empty()) {
                std::stringstream str;
                str << "nmcli device show " << adapter.name;
                std::string nmcli = exec(str.str().c_str());
                auto fields = parseNMCLI(nmcli);

                if (fields.count("GENERAL.TYPE"))
                    adapter.type = fields["GENERAL.TYPE"];
                if (fields.count("IP4.DNS[1]"))
                    adapter.dns.push_back(fields["IP4.DNS[1]"]);
                if (fields.count("GENERAL.CONNECTION"))
                    adapter.description = fields["GENERAL.CONNECTION"];
            }

            auto metric_it = metrics.find(adapter.name);
            adapter.priority = (metric_it == metrics.end()) ? -1 : metric_it->second;

            result.push_back(adapter);
        }

        return result;
    }

    std::string trim(const std::string &s) const {
        size_t start = s.find_first_not_of(" \t");
        size_t end   = s.find_last_not_of(" \t");
        if (start == std::string::npos || end == std::string::npos)
            return "";
        return s.substr(start, end - start + 1);
    }

    std::map<std::string, std::string> parseNMCLI(std::string input) const {
        std::istringstream iss(input);
        std::map<std::string, std::string> fields;

        std::string line;
        std::regex pattern(R"(^\s*([^:]+):\s*(.*)$)");
        std::smatch match;

        while (std::getline(iss, line)) {
            if (std::regex_match(line, match, pattern)) {
                std::string key = trim(match[1].str());
                std::string value = trim(match[2].str());
                fields[key] = value;
            }
        }

        return fields;
    }

    std::string prefixLengthToMask(int prefixLength) const {
        if (prefixLength < 0 || prefixLength > 32)
            return {};

        uint32_t mask = (prefixLength == 0) ? 0 : (~0u << (32 - prefixLength));

        std::ostringstream oss;
        oss  << ((mask >> 24) & 0xFF) << "."
            << ((mask >> 16) & 0xFF) << "."
            << ((mask >> 8)  & 0xFF) << "."
            << ( mask        & 0xFF);

        return oss.str();
    }

    std::map<std::string, int> ParseIpRouteOutput(const std::string& text) const {
        std::map<std::string, int> result;

        std::istringstream iss(text);
        std::string line;

        while (std::getline(iss, line)) {
            std::istringstream ls(line);

            std::string token;
            std::string iface;
            int metric = -1;

            while (ls >> token) {
                if (token == "dev") {
                    ls >> iface;               // next token is interface name
                } else if (token == "metric") {
                    ls >> metric;              // next token is metric value
                }
            }

            // Only add if both iface and metric were found
            if (!iface.empty() && metric >= 0) {
                // If interface already exists in map, keep the lowest metric
                auto it = result.find(iface);
                if (it == result.end() || metric < it->second) {
                    result[iface] = metric;
                }
            }
        }

        return result;
    }

    std::string exec(const char* cmd) const {
        // Buffer to read chunks of output
        std::array<char, 128> buffer;
        std::string result;
        // Open the pipe and ensure it closes automatically using unique_ptr
        std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd, "r"), pclose);
        if (!pipe) {
            throw std::runtime_error("popen() failed!");
        }
        // Read data in chunks until the end of the stream
        while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
            result += buffer.data();
        }
        return result;
    }


};

}

#endif // GNUNETUTIL