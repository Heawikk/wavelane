import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Search over the whole catalogue: the artists found, then the albums, then the
    tracks, as on Yandex Music. Opening an artist or an album lists their tracks.
*/
Item {
    id: root

    property bool detailOpen: true

    readonly property bool browsing: library.browseKind !== ""

    function focusSearch() {
        field.forceActiveFocus()
        field.selectAll()
    }

    // What is typed counts as soon as it is typed, including letters an input method
    // has not committed yet.
    function runSearch() {
        debounce.stop()
        library.search(field.text + field.preeditText)
    }

    // New results start at the top, with the artists in view; the header growing above the
    // list would otherwise leave it scrolled down to the tracks.
    Connections {
        target: library
        function onSearchGroupsChanged() { Qt.callLater(browser.toTop) }
        // coming back from an artist or an album, the results start at the top again
        function onBrowseChanged() { if (!root.browsing) Qt.callLater(browser.toTop) }
    }

    Component {
        id: groups

        SearchGroups {
            width: parent ? parent.width : 0
            // the list would stay scrolled to where the old height put it
            onShelfToggled: Qt.callLater(browser.toTop)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // the big input, as on Yandex Music's search page
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 72

            Rectangle {
                anchors.fill: parent
                anchors.margins: 16
                anchors.topMargin: 14
                anchors.bottomMargin: 14
                color: "transparent"
                border.color: field.activeFocus ? Theme.accent : Theme.borderStrong
                border.width: 1

                Icon {
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    glyph: Theme.iSearch
                    font.pixelSize: 16
                    color: field.activeFocus ? Theme.text : Theme.faint
                }

                TextField {
                    id: field
                    anchors.fill: parent
                    leftPadding: 44
                    rightPadding: 40
                    placeholderText: qsTr("Трек, исполнитель или альбом")
                    color: Theme.text
                    placeholderTextColor: Theme.faint
                    selectByMouse: true
                    font.family: Theme.sans
                    font.pixelSize: 16
                    background: null

                    // Searches while typing, a moment after the last key: a request per
                    // keystroke would hammer the server and the answers could arrive out of order.
                    onTextChanged: { library.closeBrowse(); debounce.restart() }
                    onPreeditTextChanged: debounce.restart()
                    Keys.onReturnPressed: {
                        root.runSearch()
                        browser.focusTable()
                    }
                    Keys.onDownPressed: browser.focusTable()
                    Keys.onEscapePressed: {
                        text = ""
                        library.clearSearch()
                    }

                    Timer {
                        id: debounce
                        interval: 180
                        onTriggered: root.runSearch()
                    }
                }

                IconButton {
                    visible: field.text !== ""
                    anchors.right: parent.right
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    glyph: Theme.iClose
                    glyphSize: 12
                    onClicked: {
                        field.text = ""
                        library.clearSearch()
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            TrackBrowser {
                id: browser
                anchors.fill: parent
                visible: !root.browsing

                model: library.searchResults
                context: "search"
                detailOpen: root.detailOpen
                topContent: groups
                topHasContent: library.searchArtists.length > 0 || library.searchAlbums.length > 0
                emptyText: library.query === "" ? qsTr("Начните печатать, чтобы найти музыку")
                           : library.searching ? qsTr("Ищем…")
                           : qsTr("Ничего не найдено")
            }

            // an artist's or an album's tracks
            ColumnLayout {
                anchors.fill: parent
                visible: root.browsing
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    spacing: 14

                    FlatButton {
                        text: qsTr("←  Назад")
                        onClicked: library.closeBrowse()
                    }
                    Text {
                        Layout.fillWidth: true
                        text: library.browseTitle
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: 20
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }
                    Mono {
                        text: library.browseKind === "artist" ? qsTr("Исполнитель") : qsTr("Альбом")
                        color: Theme.faint
                    }
                }

                TrackBrowser {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    model: library.browse
                    context: "search"
                    detailOpen: root.detailOpen
                    emptyText: library.browseLoading ? qsTr("Загрузка…") : qsTr("Здесь пока нет треков")
                }
            }
        }
    }
}
