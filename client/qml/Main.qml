import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The application window.

    It has no system frame: the bar along the top is the title bar and
    ResizeHandles give the edges back, so the app looks the same everywhere.
    Signed in, the layout follows Yandex Music's — navigation on the left, one
    page in the middle, what is playing underneath.
*/
ApplicationWindow {
    id: window

    width: 1280
    height: 800
    minimumWidth: 1200
    minimumHeight: 640
    visible: true
    title: qsTr("Wavelane")
    color: Theme.bg
    flags: Qt.Window | Qt.FramelessWindowHint

    readonly property bool maximized: visibility === Window.Maximized

    property string page: "wave"
    property bool detailOpen: true

    function showPage(name) {
        window.page = name
        if (name === "collection")
            collectionPage.refresh()
    }

    function togglePlayback() {
        if (player.hasTrack)
            player.togglePlayPause()
    }

    Connections {
        target: wave
        function onNotify(message) { toast.show(message) }
    }
    Connections {
        target: library
        function onNotify(message) { toast.show(message) }
    }
    Connections {
        target: player
        function onPlaybackFailed(message) { toast.show(message) }
    }
    Connections {
        target: auth
        function onSignedInChanged() {
            if (auth.signedIn) {
                window.page = "wave"
                wave.loadSettings()
                library.loadStats()
                library.loadCatalogue()
                library.loadLiked()
                wave.refreshProfile()
            }
        }
    }

    // --- keyboard ---------------------------------------------------------
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Ctrl+F"]
        onActivated: {
            window.page = "search"
            searchPage.focusSearch()
        }
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Ctrl+U"]
        onActivated: {
            window.showPage("collection")
            collectionPage.openUpload()
        }
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Ctrl+B"]
        onActivated: window.detailOpen = !window.detailOpen
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Space"]
        onActivated: window.togglePlayback()
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Media Play"]
        onActivated: window.togglePlayback()
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["N"]
        onActivated: transport.next()
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Media Next"]
        onActivated: transport.next()
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["L"]
        onActivated: if (player.hasTrack) library.toggleLike(player.currentTrack.id)
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["D"]
        onActivated: transport.dislike()
    }

    // leave room for the 1px window outline
    Item {
        anchors.fill: parent
        anchors.margins: window.maximized ? 0 : 1

        // --- signed out ---
        ColumnLayout {
            anchors.fill: parent
            visible: !auth.signedIn
            spacing: 0

            TitleBar {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.barHeight
                window: window
                page: window.page
            }
            LoginPage {
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // --- signed in ---
        ColumnLayout {
            anchors.fill: parent
            visible: auth.signedIn
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Sidebar {
                    Layout.preferredWidth: Theme.sidebarWidth
                    Layout.fillHeight: true
                    window: window
                    page: window.page
                    onSelected: function(name) { window.showPage(name) }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 0

                    TitleBar {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.barHeight
                        window: window
                        page: window.page
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: window.page === "search" ? 0
                                      : window.page === "wave" ? 1 : 2

                        SearchPage {
                            id: searchPage
                            detailOpen: window.detailOpen
                            onToggleDetail: window.detailOpen = !window.detailOpen
                        }
                        WavePage {}
                        CollectionPage {
                            id: collectionPage
                            detailOpen: window.detailOpen
                            onToggleDetail: window.detailOpen = !window.detailOpen
                        }
                    }
                }
            }

            TransportBar {
                id: transport
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.transportHeight
            }
        }
    }

    // the window outline, since there is no frame to provide one
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: Theme.borderStrong
        border.width: 1
        visible: !window.maximized
    }

    ResizeHandles { window: window }

    Toast { id: toast }
}
