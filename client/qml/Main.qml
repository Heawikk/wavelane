import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The application window.

    It has no system frame: the top bar is the title bar and ResizeHandles
    provide the edges, so the app looks the same on every platform instead of
    inheriting whichever window chrome the OS happens to draw.
*/
ApplicationWindow {
    id: window

    width: 1280
    height: 800
    minimumWidth: 1040
    minimumHeight: 640
    visible: true
    title: qsTr("Wavelane")
    color: Theme.bg
    flags: Qt.Window | Qt.FramelessWindowHint

    readonly property bool maximized: visibility === Window.Maximized

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
                wave.loadSettings()
                library.loadStats()
                library.loadCatalogue()
                library.loadLiked()
                wave.refreshProfile()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        // leave room for the 1px window outline
        anchors.margins: window.maximized ? 0 : 1
        spacing: 0

        TitleBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.barHeight
            window: window
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            LoginPage {
                anchors.fill: parent
                visible: !auth.signedIn
            }

            Workspace {
                anchors.fill: parent
                visible: auth.signedIn
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
