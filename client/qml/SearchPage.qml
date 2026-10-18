import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Search over the whole catalogue. */
Item {
    id: root

    property bool detailOpen: true

    function focusSearch() {
        field.forceActiveFocus()
        field.selectAll()
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

                    // Debounced: a request per keystroke would hammer the
                    // server and the answers could arrive out of order.
                    onTextChanged: debounce.restart()
                    Keys.onReturnPressed: {
                        debounce.stop()
                        library.search(text)
                        browser.focusTable()
                    }
                    Keys.onDownPressed: browser.focusTable()
                    Keys.onEscapePressed: {
                        text = ""
                        library.clearSearch()
                    }

                    Timer {
                        id: debounce
                        interval: 280
                        onTriggered: library.search(field.text)
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

        TrackBrowser {
            id: browser
            Layout.fillWidth: true
            Layout.fillHeight: true

            model: library.searchResults
            context: "search"
            detailOpen: root.detailOpen
            emptyText: library.query === "" ? qsTr("Начните печатать, чтобы найти музыку")
                       : library.searching ? qsTr("Ищем…")
                       : qsTr("Ничего не найдено")
        }
    }
}
