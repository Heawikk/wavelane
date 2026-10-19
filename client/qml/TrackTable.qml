import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The track table: a column header over a list of rows.

    Used for the wave queue, the liked list, the catalogue and search results.
    Selecting a row only reports the selection; what to show for it is the
    workspace's business.
*/
Item {
    id: root

    //! A TrackListModel.
    property var model: null
    //! Reported to the server with every play started from here.
    property string context: "search"
    //! False for the wave queue, whose order belongs to the server.
    property bool playable: true
    //! Show the playing track, and a "next up" label, above the rows.
    property bool showNowPlaying: false
    property string emptyText: ""
    property string selectedId: ""

    signal trackSelected(string trackId)
    signal deleteRequested(string trackId)

    readonly property int gap: 12
    readonly property bool wide: width > 760
    readonly property bool wider: width > 940
    readonly property int colIndex: 40
    readonly property int colArtist: Math.round(width * (wide ? 0.2 : 0.3))
    readonly property int colAlbum: wide ? Math.round(width * 0.18) : 0
    readonly property int colGenre: wider ? 130 : 0
    readonly property int colQuality: 76
    readonly property int colTime: 52

    readonly property bool nowPlayingShown: showNowPlaying && player.hasTrack
                                            && player.context === "wave"

    function select(row) {
        if (!model || row < 0 || row >= model.count)
            return
        list.currentIndex = row
        const track = model.get(row)
        // Only reported, never assigned: selectedId is bound to the workspace's
        // value, and assigning it here would silently break that binding.
        root.trackSelected(track.id)
        list.positionViewAtIndex(row, ListView.Contain)
    }

    function activate(row) {
        if (root.playable && model && row >= 0 && row < model.count)
            library.playFrom(model, row, root.context)
    }

    function selectedRow() {
        return model && selectedId !== "" ? model.indexOfId(selectedId) : -1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // --- column header ---
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: "transparent"

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.border
            }

            RowLayout {
                anchors.fill: parent
                spacing: root.gap

                Mono {
                    Layout.preferredWidth: root.colIndex
                    horizontalAlignment: Text.AlignHCenter
                    text: "#"
                    color: Theme.faint
                }
                Item { Layout.preferredWidth: 22 }
                Mono {
                    Layout.fillWidth: true
                    text: qsTr("Название")
                    color: Theme.faint
                }
                Mono {
                    Layout.preferredWidth: root.colArtist
                    text: qsTr("Исполнитель")
                    color: Theme.faint
                }
                Mono {
                    visible: root.colAlbum > 0
                    Layout.preferredWidth: root.colAlbum
                    text: qsTr("Альбом")
                    color: Theme.faint
                }
                Mono {
                    visible: root.colGenre > 0
                    Layout.preferredWidth: root.colGenre
                    text: qsTr("Жанр")
                    color: Theme.faint
                }
                Mono {
                    Layout.preferredWidth: root.colQuality
                    text: qsTr("Качество")
                    color: Theme.faint
                }
                Mono {
                    Layout.preferredWidth: root.colTime
                    horizontalAlignment: Text.AlignRight
                    text: qsTr("Время")
                    color: Theme.faint
                }
                Item { Layout.preferredWidth: 36 }
            }
        }

        // --- rows ---
        ListView {
            id: list

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.model
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            currentIndex: -1
            focus: true
            activeFocusOnTab: true

            ScrollBar.vertical: FlatScrollBar {}

            Keys.onPressed: function(event) {
                const row = root.selectedRow()
                if (event.key === Qt.Key_Down) {
                    root.select(Math.min((root.model ? root.model.count : 0) - 1, row + 1))
                    event.accepted = true
                } else if (event.key === Qt.Key_Up) {
                    root.select(Math.max(0, row - 1))
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    root.activate(row)
                    event.accepted = true
                } else if (event.key === Qt.Key_Delete && root.selectedId !== "") {
                    root.deleteRequested(root.selectedId)
                    event.accepted = true
                }
            }

            header: Column {
                width: list.width

                Item {
                    width: parent.width
                    height: root.nowPlayingShown ? 24 : 0
                    visible: root.nowPlayingShown

                    Mono {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Сейчас играет")
                        color: Theme.faint
                        font.pixelSize: 10
                    }
                }

                TrackRow {
                    width: parent.width
                    visible: root.nowPlayingShown
                    height: visible ? Theme.rowHeight : 0

                    trackId: player.currentTrack.id || ""
                    title: player.currentTrack.title || ""
                    artistName: player.currentTrack.artistName || ""
                    albumTitle: player.currentTrack.albumTitle || ""
                    coverPath: player.currentTrack.coverPath || ""
                    duration: player.currentTrack.duration || ""
                    quality: player.currentTrack.quality || ""
                    reason: player.currentTrack.reason || ""
                    genres: player.currentTrack.genres || []
                    liked: player.currentTrack.liked || false
                    isExplicit: player.currentTrack.explicit || false
                    lyricsKind: player.currentTrack.lyricsKind || "none"
                    playingNow: true
                    showReason: true
                    selected: root.selectedId === trackId

                    gap: root.gap
                    colIndex: root.colIndex
                    colArtist: root.colArtist
                    colAlbum: root.colAlbum
                    colGenre: root.colGenre
                    colQuality: root.colQuality
                    colTime: root.colTime

                    onClicked: root.trackSelected(trackId)
                    onLikeToggled: library.toggleLike(trackId)
                }

                Item {
                    width: parent.width
                    height: root.nowPlayingShown && root.model && root.model.count > 0 ? 28 : 0
                    visible: height > 0

                    Mono {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 4
                        text: qsTr("Далее в волне")
                        color: Theme.faint
                        font.pixelSize: 10
                    }
                }
            }

            delegate: TrackRow {
                id: row

                width: ListView.view.width
                rowNumber: index + 1
                trackId: model.trackId
                title: model.title
                artistName: model.artistName
                albumTitle: model.albumTitle
                coverPath: model.coverPath
                duration: model.duration
                quality: model.quality
                reason: model.reason
                genres: model.genres
                liked: model.liked
                isExplicit: model.isExplicit
                lyricsKind: model.lyricsKind
                selected: root.selectedId === trackId
                playingNow: player.hasTrack && player.currentTrack.id === trackId
                            && !root.showNowPlaying
                showReason: root.showNowPlaying

                gap: root.gap
                colIndex: root.colIndex
                colArtist: root.colArtist
                colAlbum: root.colAlbum
                colGenre: root.colGenre
                colQuality: root.colQuality
                colTime: root.colTime

                onClicked: {
                    list.forceActiveFocus()
                    root.select(index)
                }
                onActivated: {
                    root.select(index)
                    root.activate(index)
                }
                onLikeToggled: library.toggleLike(trackId)
            }
        }
    }

    // Shown over the empty list rather than as another layout item, which
    // would compete with the list for the height.
    Mono {
        anchors.centerIn: parent
        width: parent.width * 0.7
        visible: root.model && root.model.count === 0 && !root.nowPlayingShown
        text: root.emptyText
        color: Theme.faint
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideNone
        lineHeight: 1.4
    }
}
