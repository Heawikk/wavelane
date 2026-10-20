import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The application on a phone.

    The same look as the desktop (flat, dark, small monospace capitals), but
    laid out for a thumb: a strip with the page title above, the page in the
    middle, what is playing and the three tabs underneath. Tapping what is
    playing opens the full player over everything.
*/
ApplicationWindow {
    id: window

    // These only matter when the phone layout is shown on a desktop for testing.
    width: 412
    height: 880
    visible: true
    title: qsTr("Wavelane")
    color: Theme.bg

    property string page: "wave"
    property bool nowPlayingOpen: false
    property bool lyricsOpen: false

    onLyricsOpenChanged: lyrics.active = lyricsOpen && auth.signedIn

    readonly property string pageNumber: page === "search" ? "01" : page === "wave" ? "02"
                                         : page === "collection" ? "03" : "04"
    readonly property string pageTitle: page === "search" ? qsTr("Поиск")
                                        : page === "wave" ? qsTr("Моя волна")
                                        : page === "collection" ? qsTr("Коллекция")
                                        : qsTr("Админ меню")
    //! The pages in the order of the tabs; the last is for administrators only.
    readonly property var pageOrder: auth.isAdmin ? ["search", "wave", "collection", "admin"]
                                                  : ["search", "wave", "collection"]

    function showPage(name) {
        window.page = name
        if (name === "collection")
            collectionPage.refresh()
        else if (name === "admin")
            adminPage.refresh()
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
        target: lyrics
        function onNotify(message) { toast.show(message) }
    }
    Connections {
        target: player
        function onPlaybackFailed(message) { toast.show(message) }
    }
    function loadEverything() {
        wave.loadSettings()
        library.loadStats()
        library.loadCatalogue()
        library.loadLiked()
        wave.refreshProfile()
    }

    Connections {
        target: auth
        // The app was opened with the server away; now it has answered.
        function onSessionResumed() { window.loadEverything() }
        // The admin menu is for administrators: leave it if that stops being true.
        function onUserChanged() {
            if (!auth.isAdmin && window.page === "admin")
                window.page = "wave"
        }
        function onSignedInChanged() {
            if (auth.signedIn) {
                // the keyboard from the sign-in form should not stay up
                Qt.inputMethod.hide()
                window.page = "wave"
                window.loadEverything()
            } else {
                window.nowPlayingOpen = false
                window.lyricsOpen = false
            }
        }
    }

    // The Back button first closes what is on top, and only then leaves the app.
    onClosing: function(close) {
        if (lyricsOpen) {
            lyricsOpen = false
            close.accepted = false
        } else if (nowPlayingOpen) {
            nowPlayingOpen = false
            close.accepted = false
        } else if (page === "search" && library.browseKind !== "") {
            // an artist or an album is open: Back returns to the results
            library.closeBrowse()
            close.accepted = false
        } else if (page !== "wave" && auth.signedIn) {
            page = "wave"
            close.accepted = false
        } else if (player.hasTrack) {
            // Back from the main page leaves the app running, like any music player.
            media.moveToBackground()
            close.accepted = false
        }
    }

    // --- signed out ---
    LoginPage {
        anchors.fill: parent
        visible: !auth.signedIn && !auth.restoring
    }

    // the stored session is being checked: a short, plain screen instead of the sign-in form flashing by
    Rectangle {
        anchors.fill: parent
        visible: !auth.signedIn && auth.restoring
        color: Theme.bg

        Column {
            anchors.centerIn: parent
            spacing: 14

            Logo {
                size: 64
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Mono {
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Подключение…")
                color: Theme.faint
            }
        }
    }

    // --- signed in ---
    ColumnLayout {
        anchors.fill: parent
        visible: auth.signedIn
        spacing: 0
        // The full player covers this, but touches (unlike mouse clicks) still reach the handlers
        // underneath it, so the pages must be switched off while it is open.
        enabled: !window.nowPlayingOpen

        // the strip with the page heading and its buttons
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: window.page === "wave" ? "transparent" : Theme.bg
            z: 2

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.border
                visible: window.page !== "wave"
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 4
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 18
                    color: Theme.accent

                    Mono {
                        anchors.centerIn: parent
                        text: window.pageNumber
                        color: "white"
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }
                }
                Mono {
                    Layout.fillWidth: true
                    text: window.pageTitle
                    color: Theme.text
                    font.weight: Font.DemiBold
                    font.pixelSize: 13
                }
                IconButton {
                    visible: window.page === "wave"
                    size: 48
                    glyph: Theme.iTune
                    glyphSize: 20
                    onClicked: tuneSheet.open()
                }
                IconButton {
                    size: 48
                    glyph: Theme.iSettings
                    glyphSize: 20
                    onClicked: settingsDialog.open()
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            // the wave's glow runs behind the strip above it
            Layout.topMargin: window.page === "wave" ? -52 : 0

            StackLayout {
                anchors.fill: parent
                currentIndex: window.page === "search" ? 0 : window.page === "wave" ? 1
                              : window.page === "collection" ? 2 : 3

                MobileSearchPage { id: searchPage }
                WavePage { id: wavePage }
                MobileCollectionPage { id: collectionPage }
                MobileAdminPage { id: adminPage }
            }

            OfflineBadge {
                width: parent.width
                // under the strip with the buttons, which the wave page's glow runs behind
                y: window.page === "wave" ? 52 : 0
                z: 3
                wanted: auth.signedIn
            }

            // A swipe sideways turns to the next page along the tabs. Only sideways travel counts,
            // so scrolling a list is left alone.
            DragHandler {
                id: pageSwipe

                property real travelX: 0

                target: null
                yAxis.enabled: false
                dragThreshold: 30

                onActiveChanged: {
                    if (active) {
                        travelX = 0
                        return
                    }
                    const order = window.pageOrder
                    const at = order.indexOf(window.page)
                    if (travelX < -80 && at < order.length - 1)
                        window.showPage(order[at + 1])
                    else if (travelX > 80 && at > 0)
                        window.showPage(order[at - 1])
                }
                onActiveTranslationChanged: if (active) travelX = activeTranslation.x
            }
        }

        MiniPlayer {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            visible: player.hasTrack
            onOpened: window.nowPlayingOpen = true
        }

        BottomNav {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            page: window.page
            onSelected: function(name) { window.showPage(name) }
        }
    }

    // --- the full player, over everything ---
    NowPlaying {
        id: nowPlaying
        width: parent.width
        height: parent.height
        // pull is how far a finger has dragged the player down; it follows the finger exactly
        y: (window.nowPlayingOpen && auth.signedIn ? 0 : height) + pull
        visible: y < height
        lyricsOpen: window.lyricsOpen
        onClosed: {
            window.lyricsOpen = false
            window.nowPlayingOpen = false
        }
        onLyricsToggled: window.lyricsOpen = !window.lyricsOpen

        Behavior on y {
            enabled: !nowPlaying.dragging
            NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
        }
    }

    MobileTuneSheet { id: tuneSheet }
    SettingsDialog { id: settingsDialog }

    Toast { id: toast }
}
