import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Search over the whole catalogue, on a phone. */
Item {
    id: root

    readonly property bool browsing: library.browseKind !== ""

    function focusSearch() { field.forceActiveFocus() }

    // What is typed counts as soon as it is typed, including letters the keyboard has not
    // committed yet.
    function runSearch() {
        debounce.stop()
        library.search(field.text + field.preeditText)
    }

    // New results start at the top, with the artists in view.
    Connections {
        target: library
        function onSearchGroupsChanged() { Qt.callLater(results.toTop) }
        // coming back from an artist or an album, the results start at the top again
        function onBrowseChanged() { if (!root.browsing) Qt.callLater(results.toTop) }
    }

    Component {
        id: groups

        SearchGroups {
            width: parent ? parent.width : 0
            scrollable: true
            cardSize: 128
            margin: 14
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            Rectangle {
                anchors.fill: parent
                anchors.margins: 12
                color: "transparent"
                border.color: field.activeFocus ? Theme.accent : Theme.borderStrong
                border.width: 1

                Icon {
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    glyph: Theme.iSearch
                    font.pixelSize: 18
                    color: field.activeFocus ? Theme.text : Theme.faint
                }

                TextField {
                    id: field
                    anchors.fill: parent
                    leftPadding: 44
                    rightPadding: 44
                    placeholderText: qsTr("Трек, исполнитель или альбом")
                    color: Theme.text
                    placeholderTextColor: Theme.faint
                    font.family: Theme.sans
                    font.pixelSize: 16
                    background: null
                    inputMethodHints: Qt.ImhNoPredictiveText

                    // Searches while typing, a moment after the last key: a request per
                    // keystroke would hammer the server.
                    onTextChanged: { library.closeBrowse(); debounce.restart() }
                    onPreeditTextChanged: debounce.restart()
                    onAccepted: {
                        root.runSearch()
                        field.focus = false
                    }

                    Timer {
                        id: debounce
                        interval: 220
                        onTriggered: root.runSearch()
                    }
                }

                IconButton {
                    visible: field.text !== ""
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    size: 48
                    glyph: Theme.iClose
                    glyphSize: 14
                    onClicked: {
                        field.text = ""
                        library.clearSearch()
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        // an artist's or an album's tracks, with a way back
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            visible: root.browsing
            color: "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 14
                spacing: 4

                IconButton {
                    size: 44
                    glyph: Theme.iChevronUp
                    glyphSize: 20
                    rotation: -90
                    onClicked: library.closeBrowse()
                }
                Text {
                    Layout.fillWidth: true
                    text: library.browseTitle
                    color: Theme.text
                    font.family: Theme.sans
                    font.pixelSize: 17
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
            }
        }

        MobileTrackList {
            id: results
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.browsing

            model: library.searchResults
            context: "search"
            topContent: groups
            topHasContent: library.searchArtists.length > 0 || library.searchAlbums.length > 0
            emptyText: library.query === "" ? qsTr("Начните печатать, чтобы найти музыку")
                       : library.searching ? qsTr("Ищем…")
                       : qsTr("Ничего не найдено")
        }

        MobileTrackList {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.browsing

            model: library.browse
            context: "search"
            emptyText: library.browseLoading ? qsTr("Загрузка…") : qsTr("Здесь пока нет треков")
        }
    }
}
