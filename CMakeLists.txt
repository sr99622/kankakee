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

cmake_minimum_required(VERSION 3.17)

project(kankakee VERSION 1.0.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DSOCKLEN_T=socklen_t -D__STDC_CONSTANT_MACROS")

#find_package(LibLZMA REQUIRED)

add_subdirectory(pybind11)

pybind11_add_module(kankakee
    src/kankakee.cpp
)

#target_link_libraries(kankakee PRIVATE
#    LibLZMA::LibLZMA
#)

if (WIN32)
    target_link_libraries(kankakee PRIVATE
        wsock32
        ws2_32    
    )
endif()

target_include_directories(kankakee PUBLIC
    include
)
