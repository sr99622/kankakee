# kankakee

A Server/Client python module designed for use in [OnvifGUI](https://github.com/sr99622/libonvif) to provide remote access to a centralized Camera Server.

Copyright (c) 2024  Stephen Rhodes

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

# nlohmann/json

## License

<img align="right" src="https://149753425.v2.pressablecdn.com/wp-content/uploads/2009/06/OSIApproved_100X125.png" alt="OSI approved license">

The class is licensed under the [MIT License](https://opensource.org/licenses/MIT):

Copyright &copy; 2013-2026 [Niels Lohmann](https://nlohmann.me)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

* * *

- The class contains the UTF-8 Decoder from Bjoern Hoehrmann which is licensed under the [MIT License](https://opensource.org/licenses/MIT) (see above). Copyright &copy; 2008-2009 [Björn Hoehrmann](https://bjoern.hoehrmann.de/) <bjoern@hoehrmann.de>
- The class contains a slightly modified version of the Grisu2 algorithm from Florian Loitsch which is licensed under the [MIT License](https://opensource.org/licenses/MIT) (see above). Copyright &copy; 2009 [Florian Loitsch](https://florian.loitsch.com/)
- The class contains a copy of [Hedley](https://nemequ.github.io/hedley/) from Evan Nemerson which is licensed as [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/).
- The class contains parts of [Google Abseil](https://github.com/abseil/abseil-cpp) which is licensed under the [Apache 2.0 License](https://opensource.org/licenses/Apache-2.0).

<img align="right" src="https://git.fsfe.org/reuse/reuse-ci/raw/branch/master/reuse-horizontal.png" alt="REUSE Software">

The library is compliant to version 3.3 of the [**REUSE specification**](https://reuse.software):

- Every source file contains an SPDX copyright header.
- The full text of all licenses used in the repository can be found in the `LICENSES` folder.
- File `.reuse/dep5` contains an overview of all files' copyrights and licenses.
- Run `pipx run reuse lint` to verify the project's REUSE compliance and `pipx run reuse spdx` to generate a SPDX SBOM.