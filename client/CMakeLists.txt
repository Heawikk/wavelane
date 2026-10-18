cmake_minimum_required(VERSION 3.21)

project(Wavelane VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_INCLUDE_CURRENT_DIR ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS
    Core
    Gui
    Quick
    QuickControls2
    Network
    Multimedia
)

qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(wavelane
    src/main.cpp
    src/Settings.h           src/Settings.cpp
    src/ApiClient.h          src/ApiClient.cpp
    src/AuthController.h     src/AuthController.cpp
    src/Track.h              src/Track.cpp
    src/TrackListModel.h     src/TrackListModel.cpp
    src/Player.h             src/Player.cpp
    src/WaveController.h     src/WaveController.cpp
    src/LibraryController.h  src/LibraryController.cpp
)

# Theme is a singleton so every page can reach the palette without plumbing it
# through properties.
set_source_files_properties(qml/Theme.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)

qt_add_qml_module(wavelane
    URI Wavelane
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/Theme.qml
        qml/Mono.qml
        qml/Icon.qml
        qml/IconButton.qml
        qml/RoundButton.qml
        qml/FlatButton.qml
        qml/Segmented.qml
        qml/FlatCombo.qml
        qml/FlatScrollBar.qml
        qml/SectionHeader.qml
        qml/Kbd.qml
        qml/CoverArt.qml
        qml/Toast.qml
        qml/WindowButton.qml
        qml/ResizeHandles.qml
        qml/TitleBar.qml
        qml/Sidebar.qml
        qml/LoginPage.qml
        qml/WavePage.qml
        qml/SearchPage.qml
        qml/CollectionPage.qml
        qml/TrackBrowser.qml
        qml/TrackTable.qml
        qml/TrackRow.qml
        qml/DetailPanel.qml
        qml/TransportBar.qml
)

target_include_directories(wavelane PRIVATE src)

target_link_libraries(wavelane PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Quick
    Qt6::QuickControls2
    Qt6::Network
    Qt6::Multimedia
)

set_target_properties(wavelane PROPERTIES
    # A GUI app should not open a console window on Windows.
    WIN32_EXECUTABLE TRUE
    MACOSX_BUNDLE TRUE
)

if(MSVC)
    target_compile_options(wavelane PRIVATE /W4 /permissive- /utf-8)
else()
    target_compile_options(wavelane PRIVATE -Wall -Wextra)
endif()

install(TARGETS wavelane
    BUNDLE  DESTINATION .
    RUNTIME DESTINATION bin
)
