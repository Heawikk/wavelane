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
    minimumWidth: 1280
    minimumHeight: 640
    visible: true
    title: qsTr("Wavelane")
    color: Theme.bg
    flags: Qt.Window | Qt.FramelessWindowHint

    readonly property bool maximized: visibility === Window.Maximized

    property string page: "wave"
    property bool detailOpen: true
    //! The words of the playing song cover the page while this is set.
    property bool lyricsOpen: false

    onPageChanged: lyricsOpen = false
    onLyricsOpenChanged: lyrics.active = lyricsOpen && auth.signedIn

    function showPage(name) {
        window.page = name
        if (name === "collection")
            collectionPage.refresh()
        else if (name === "admin")
            adminPage.refresh()
    }

    //! Sparks from the like or dislike button to the wave's blobs (or up, off the wave page).
    function react(kind) {
        const button = kind === "like" ? transport.likeButton : transport.dislikeButton
        const onWave = window.page === "wave" && !window.lyricsOpen
        reactionFx.play(kind, button, onWave ? wavePage : null)
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
        function onConflictsFound() { conflictDialog.open() }
        // a name was clicked somewhere: its page is in the search
        function onArtistShown() {
            window.lyricsOpen = false
            window.showPage("search")
        }
        function onReactionChanged(trackId, liked, disliked) {
            if (liked)
                window.react("like")
            else if (disliked)
                window.react("dislike")
        }
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
        if (auth.isAdmin) {
            // an import may have been left running, and answers may be pending
            library.restoreImport()
            library.loadConflicts()
        }
    }

    Connections {
        target: auth
        // The app was opened with the server away; now it has answered.
        function onSessionResumed() { window.loadEverything() }
        function onSignedInChanged() {
            if (auth.signedIn) {
                window.page = "wave"
                window.loadEverything()
            }
        }
        // The admin menu is for administrators: leave it if that stops being true.
        function onUserChanged() {
            if (!auth.isAdmin && window.page === "admin")
                window.page = "wave"
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
        enabled: auth.signedIn && auth.isAdmin
        sequences: ["Ctrl+U"]
        onActivated: {
            window.showPage("admin")
            adminPage.openUpload()
        }
    }
    Shortcut {
        enabled: auth.signedIn
        sequences: ["Ctrl+B"]
        onActivated: window.detailOpen = !window.detailOpen
    }
    Shortcut {
        enabled: auth.signedIn && window.lyricsOpen && !lyricsEditor.opened
        sequences: ["Escape"]
        onActivated: window.lyricsOpen = false
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
                    onOpenSettings: settingsDialog.open()
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
                        detailOpen: window.detailOpen
                        collectionTab: collectionPage.tab
                        adminTab: adminPage.tab
                        onToggleDetail: window.detailOpen = !window.detailOpen
                    }

                    OfflineBadge {
                        Layout.fillWidth: true
                        Layout.preferredHeight: shown ? implicitHeight : 0
                        wanted: auth.signedIn
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        StackLayout {
                            anchors.fill: parent
                            currentIndex: window.page === "search" ? 0
                                          : window.page === "wave" ? 1
                                          : window.page === "collection" ? 2 : 3

                            SearchPage {
                                id: searchPage
                                detailOpen: window.detailOpen
                            }
                            WavePage { id: wavePage }
                            CollectionPage {
                                id: collectionPage
                                detailOpen: window.detailOpen
                            }
                            AdminPage {
                                id: adminPage
                                detailOpen: window.detailOpen
                                onShowConflicts: conflictDialog.open()
                            }
                        }

                        LyricsView {
                            anchors.fill: parent
                            visible: window.lyricsOpen
                            onEditRequested: lyricsEditor.openForCurrent()
                            onCloseRequested: window.lyricsOpen = false
                        }
                    }
                }
            }

            TransportBar {
                id: transport
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.transportHeight
                lyricsOpen: window.lyricsOpen
                onToggleLyrics: window.lyricsOpen = !window.lyricsOpen
                onWaveDisliked: window.react("dislike")
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

    ReactionFx {
        id: reactionFx
        anchors.fill: parent
        z: 10
        onArrived: function(kind) {
            wavePage.pulse(kind === "like" ? "#ff1f4d" : "#7d828f", kind === "like" ? 1.0 : 0.8)
        }
    }

    ResizeHandles { window: window }

    ConflictDialog { id: conflictDialog }
    SettingsDialog { id: settingsDialog }
    LyricsEditor { id: lyricsEditor }

    Toast { id: toast }
}
