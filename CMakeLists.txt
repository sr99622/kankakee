#*******************************************************************************
# kankakee/CMakeLists.txt
#
# Copyright (c) 2024 Stephen Rhodes 
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#******************************************************************************/

cmake_minimum_required(VERSION 3.20)

project(kankakee VERSION 1.0.3)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DSOCKLEN_T=socklen_t -D__STDC_CONSTANT_MACROS")
include(GNUInstallDirs)
set(CMAKE_INSTALL_INCLUDEDIR "include/${CMAKE_LIBRARY_ARCHITECTURE}")

if(WIN32)
    add_compile_options("/EHsc")
    add_compile_definitions("NO_GETIFADDRS")
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS TRUE)
    set(BUILD_SHARED_LIBS TRUE)
endif()

add_subdirectory(pybind11)

pybind11_add_module(kankakee
    src/kankakee.cpp
)

if (WIN32)
    target_link_libraries(kankakee PRIVATE
        wsock32
        ws2_32    
    )
endif()

target_include_directories(kankakee PUBLIC
    include
)
