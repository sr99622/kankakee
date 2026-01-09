/********************************************************************
* kankakee/src/kankakee.cpp
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

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/operators.h>
#include <pybind11/functional.h>

#include "Broadcaster.h"

#ifdef _WIN32
    #include "WinClient.h"
    #include "WinServer.h"
    #include "WinListener.h"
#else
    #include "Client.h"
    #include "Listener.h"
#endif

#ifdef __linux__
    #include "Server.h"
#endif

#ifdef __APPLE__
    #include "MacServer.h"
#endif


namespace py = pybind11;

namespace kankakee
{

PYBIND11_MODULE(kankakee, m)
{
    m.doc() = "pybind11 client/server plugin";
    py::class_<Server>(m, "Server")
        .def(py::init<const std::string&, int>())
        .def("start", &Server::start)
        .def("stop", &Server::stop)
        .def_readwrite("errorCallback", &Server::errorCallback)
        .def_readwrite("serverCallback", &Server::serverCallback)
        .def_readwrite("running", &Server::running);

    py::class_<Client>(m, "Client")
        .def(py::init<const std::string&, int>())
        .def("transmit", &Client::transmit)
        .def("setEndpoint", &Client::setEndpoint)
        .def_readwrite("timeout", &Client::timeout)
        .def_readwrite("errorCallback", &Client::errorCallback)
        .def_readwrite("clientCallback", &Client::clientCallback);

    py::class_<Broadcaster>(m, "Broadcaster")
        .def(py::init<const std::vector<std::string>&>())
        .def("send", &Broadcaster::send)
        .def("enableLoopback", &Broadcaster::enableLoopback)
        .def_readwrite("errorCallback", &Broadcaster::errorCallback);

    py::class_<Listener>(m, "Listener")
        .def(py::init<const std::vector<std::string>&>())
        .def("start", &Listener::start)
        .def("stop", &Listener::stop)
        .def_readwrite("running", &Listener::running)
        .def_readwrite("errorCallback", &Listener::errorCallback)
        .def_readwrite("listenCallback", &Listener::listenCallback);

    m.attr("__version__") = "1.0.4";
}

}