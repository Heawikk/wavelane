cmake_minimum_required(VERSION 3.21)

project(Wavelane VERSION 1.0.0 LANGUAGES CXX)

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
    ShaderTools
)

qt_standard_project_setup(REQUIRES 6.5)

# The resource compiler is needed for the executable's icon on Windows.
if(WIN32)
    enable_language(RC)
endif()

qt_add_executable(wavelane
    src/main.cpp
    src/AppIdentity.h        src/AppIdentity.cpp
    src/Settings.h           src/Settings.cpp
    src/ApiClient.h          src/ApiClient.cpp
    src/AuthController.h     src/AuthController.cpp
    src/UpdateController.h   src/UpdateController.cpp
    src/Track.h              src/Track.cpp
    src/TrackListModel.h     src/TrackListModel.cpp
    src/AudioTap.h           src/AudioTap.cpp
    src/LyricsController.h   src/LyricsController.cpp
    src/MediaSession.h       src/MediaSession.cpp
    src/DiscordIpc.h         src/DiscordIpc.cpp
    src/DiscordPresence.h    src/DiscordPresence.cpp
    src/DiscordRelay.h       src/DiscordRelay.cpp
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
        qml/OfflineBadge.qml
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
        qml/ConfirmDialog.qml
        qml/ConflictDialog.qml
        qml/ImportBanner.qml
        qml/VibeBackground.qml
        qml/Equalizer.qml
        qml/Visualizer.qml
        qml/RingVisualizer.qml
        qml/Chip.qml
        qml/MobileTrackList.qml
        qml/MiniPlayer.qml
        qml/BottomNav.qml
        qml/NowPlaying.qml
        qml/MobileTuneSheet.qml
        qml/MobileSearchPage.qml
        qml/MobileCollectionPage.qml
        qml/MobileMain.qml
        qml/Logo.qml
        qml/LyricsView.qml
        qml/LyricsEditor.qml
        qml/LyricsBadge.qml
        qml/ReactionFx.qml
        qml/FlatField.qml
        qml/SettingsDialog.qml
)

# Compiled for every graphics backend Qt supports, so the same file runs on
# Direct3D, Vulkan, Metal and OpenGL.
qt_add_shaders(wavelane "wavelane_shaders"
    PREFIX "/shaders"
    BASE "${CMAKE_CURRENT_SOURCE_DIR}/qml/shaders"
    FILES qml/shaders/vibe.frag
)

# The window icon, at the sizes the shell asks for.
qt_add_resources(wavelane "app_icons"
    PREFIX "/icons"
    BASE "${CMAKE_CURRENT_SOURCE_DIR}/resources"
    FILES
        resources/wavelane-16.png
        resources/wavelane-24.png
        resources/wavelane-32.png
        resources/wavelane-48.png
        resources/wavelane-64.png
        resources/wavelane-128.png
        resources/wavelane-256.png
)

# The fonts the design depends on, so every platform draws it the same way: the
# monospace of the labels (Cascadia Mono, OFL) and the icon font used where the
# system has no Segoe icons, i.e. on Android (Material Icons, Apache 2.0).
qt_add_resources(wavelane "app_fonts"
    PREFIX "/fonts"
    BASE "${CMAKE_CURRENT_SOURCE_DIR}/resources/fonts"
    FILES
        resources/fonts/CascadiaMono-Regular.ttf
        resources/fonts/CascadiaMono-SemiBold.ttf
        resources/fonts/MaterialIcons-Regular.ttf
)

# ...and the icon of the .exe itself, which Explorer and the taskbar read.
if(WIN32)
    configure_file(resources/wavelane.rc.in "${CMAKE_CURRENT_BINARY_DIR}/wavelane.rc" @ONLY)
    target_sources(wavelane PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/wavelane.rc")
endif()

target_include_directories(wavelane PRIVATE src)

# Where updates are looked for: the latest release of this GitHub repository.
set(WAVELANE_UPDATE_REPO "Heawikk/wavelane" CACHE STRING "GitHub repository (owner/name) that publishes the releases")
target_compile_definitions(wavelane PRIVATE
    WAVELANE_VERSION="${PROJECT_VERSION}"
    WAVELANE_UPDATE_REPO="${WAVELANE_UPDATE_REPO}")

target_link_libraries(wavelane PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Quick
    Qt6::QuickControls2
    Qt6::Network
    Qt6::Multimedia
)

# The Windows media controls are a WinRT API.
if(WIN32)
    target_link_libraries(wavelane PRIVATE windowsapp shell32 ole32 propsys)
endif()

if(ANDROID)
    # Must grow with every release, or the system refuses to install it over the old one.
    math(EXPR WAVELANE_ANDROID_VERSION_CODE
        "${PROJECT_VERSION_MAJOR} * 10000 + ${PROJECT_VERSION_MINOR} * 100 + ${PROJECT_VERSION_PATCH}")
    # The event loop of the main thread is replaced (see main.cpp), which needs a private header.
    target_link_libraries(wavelane PRIVATE Qt6::GuiPrivate)
    # The manifest (permissions, cleartext http, portrait) and the launcher icons.
    set_property(TARGET wavelane PROPERTY QT_ANDROID_PACKAGE_SOURCE_DIR
        "${CMAKE_CURRENT_SOURCE_DIR}/android")
    set_property(TARGET wavelane PROPERTY QT_ANDROID_VERSION_NAME "${PROJECT_VERSION}")
    set_property(TARGET wavelane PROPERTY QT_ANDROID_VERSION_CODE ${WAVELANE_ANDROID_VERSION_CODE})
    set_property(TARGET wavelane PROPERTY QT_ANDROID_MIN_SDK_VERSION 28)
    set_property(TARGET wavelane PROPERTY QT_ANDROID_TARGET_SDK_VERSION 34)
endif()

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
    LIBRARY DESTINATION lib
)
