import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The signed-in screen: sources, the track table, the detail panel and the
    console panel underneath, with the transport strip at the very bottom.

    This is also where the keyboard lives, since the shortcuts cut across every
    panel.
*/
Item {
    id: root

    property string source: "wave"
    property bool detailOpen: true
    property string selectedId: ""

    readonly property bool searchActive: library.query !== ""

    readonly property var activeModel: searchActive ? library.searchResults
                                       : source === "liked" ? library.liked
                                       : source === "catalogue" ? library.catalogue
                                       : wave.queue

    readonly property string title: searchActive ? qsTr("Поиск")
                                    : source === "liked" ? qsTr("Избранное")
                                    : source === "catalogue" ? qsTr("Каталог")
                                    : qsTr("Моя волна")

    readonly property string emptyText: searchActive
        ? (library.searching ? qsTr("Ищем…") : qsTr("Ничего не найдено"))
        : source === "liked" ? qsTr("Пока ничего не нравится. Ставьте ♥ — и треки появятся здесь.")
        : source === "catalogue" ? qsTr("Каталог пуст. Загрузите аудиофайлы: сервер прочитает теги, обложки и проанализирует звук.")
        : (wave.statusMessage !== "" ? wave.statusMessage
           : qsTr("Нажмите «Слушать волну» — она подберёт музыку под ваш вкус."))

    // Look the selected track up wherever it lives. The revisions are read
    // only to make the binding re-run when any of those lists changes.
    readonly property var detailTrack: {
        const dependencies = activeModel.revision + wave.history.revision + wave.queue.revision
                             + library.liked.revision + library.catalogue.revision
                             + library.searchResults.revision
        const playing = player.hasTrack ? player.currentTrack : null

        if (selectedId === "")
            return playing

        const models = [activeModel, wave.history, wave.queue, library.catalogue,
                        library.liked, library.searchResults]
        for (let i = 0; i < models.length; ++i) {
            const row = models[i].indexOfId(selectedId)
            if (row >= 0)
                return models[i].get(row)
        }
        // Selected something that is no longer in any list: show what is playing.
        return playing
    }

    onDetailTrackChanged: if (detailTrack && detailTrack.id) library.loadDetail(detailTrack.id)

    function focusSearch() {
        searchField.forceActiveFocus()
        searchField.selectAll()
    }

    function togglePlayback() {
        if (player.hasTrack)
            player.togglePlayPause()
    }

    function playSelected() {
        if (source === "wave" && !searchActive) {
            wave.start()
            return
        }
        const row = activeModel.indexOfId(selectedId)
        if (row >= 0)
            library.playFrom(activeModel, row, searchActive ? "search" : source)
    }

    Component.onCompleted: wave.refreshProfile()

    // --- keyboard ---------------------------------------------------------
    Shortcut { enabled: root.visible; sequences: ["Ctrl+F"]; onActivated: root.focusSearch() }
    Shortcut { enabled: root.visible; sequences: ["Ctrl+J"]; onActivated: bottom.toggle() }
    Shortcut {
        enabled: root.visible
        sequences: ["Ctrl+B"]
        onActivated: root.detailOpen = !root.detailOpen
    }
    Shortcut { enabled: root.visible; sequences: ["Ctrl+U"]; onActivated: sources.openUpload() }
    Shortcut { enabled: root.visible; sequences: ["Space"]; onActivated: root.togglePlayback() }
    Shortcut { enabled: root.visible; sequences: ["N"]; onActivated: transport.next() }
    Shortcut {
        enabled: root.visible
        sequences: ["L"]
        onActivated: if (player.hasTrack) library.toggleLike(player.currentTrack.id)
    }
    Shortcut { enabled: root.visible; sequences: ["D"]; onActivated: transport.dislike() }
    Shortcut {
        enabled: root.visible
        sequences: ["Media Play"]
        onActivated: root.togglePlayback()
    }
    Shortcut { enabled: root.visible; sequences: ["Media Next"]; onActivated: transport.next() }
    Shortcut {
        sequences: ["Escape"]
        enabled: root.visible && (root.searchActive || searchField.activeFocus)
        onActivated: {
            searchField.text = ""
            library.clearSearch()
            table.forceActiveFocus()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // --- 01 sources ---
            SourcesPanel {
                id: sources
                Layout.preferredWidth: Theme.sidebarWidth
                Layout.fillHeight: true
                source: root.source
                onSelected: function(value) {
                    root.source = value
                    root.selectedId = ""
                    searchField.text = ""
                    library.clearSearch()
                    if (value === "liked")
                        library.loadLiked()
                    else if (value === "catalogue")
                        library.loadCatalogue()
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                color: Theme.border
            }

            // --- 02 tracks ---
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                SectionHeader {
                    Layout.fillWidth: true
                    number: "02"
                    title: root.title

                    BusyIndicator {
                        running: library.searching || wave.loading
                        visible: running
                        implicitWidth: 18
                        implicitHeight: 18
                    }

                    Rectangle {
                        width: 260
                        height: 26
                        color: "transparent"
                        border.color: searchField.activeFocus ? Theme.faint : Theme.borderStrong
                        border.width: 1

                        Icon {
                            x: 8
                            anchors.verticalCenter: parent.verticalCenter
                            glyph: Theme.iSearch
                            font.pixelSize: 12
                            color: Theme.faint
                        }

                        TextField {
                            id: searchField
                            anchors.fill: parent
                            leftPadding: 28
                            rightPadding: 26
                            placeholderText: qsTr("Поиск · Ctrl+F")
                            color: Theme.text
                            placeholderTextColor: Theme.faint
                            selectByMouse: true
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            background: null

                            // Debounced: a request per keystroke would hammer the
                            // server and the answers could arrive out of order.
                            onTextChanged: debounce.restart()
                            Keys.onReturnPressed: {
                                debounce.stop()
                                library.search(text)
                                table.forceActiveFocus()
                            }
                            Keys.onDownPressed: table.forceActiveFocus()

                            Timer {
                                id: debounce
                                interval: 280
                                onTriggered: library.search(searchField.text)
                            }
                        }

                        IconButton {
                            visible: searchField.text !== ""
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            size: 24
                            glyphSize: 11
                            glyph: Theme.iClose
                            onClicked: {
                                searchField.text = ""
                                library.clearSearch()
                            }
                        }
                    }

                    IconButton {
                        glyph: Theme.iPanel
                        active: root.detailOpen
                        activeColor: Theme.accentText
                        tooltip: qsTr("Панель деталей · Ctrl+B")
                        onClicked: root.detailOpen = !root.detailOpen
                    }
                }

                TrackTable {
                    id: table
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    model: root.activeModel
                    context: root.searchActive ? "search" : root.source
                    playable: root.searchActive || root.source !== "wave"
                    showNowPlaying: root.source === "wave" && !root.searchActive
                    emptyText: root.emptyText
                    selectedId: root.selectedId
                    onTrackSelected: function(trackId) { root.selectedId = trackId }
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                color: Theme.border
                visible: root.detailOpen
            }

            // --- 03 detail ---
            DetailPanel {
                Layout.preferredWidth: Theme.detailWidth
                Layout.fillHeight: true
                visible: root.detailOpen
                track: root.detailTrack
                onPlayRequested: root.playSelected()
            }
        }

        // --- 04 console ---
        BottomPanel {
            id: bottom
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            onToggle: open = !open
        }

        TransportBar {
            id: transport
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.transportHeight
        }
    }
}
