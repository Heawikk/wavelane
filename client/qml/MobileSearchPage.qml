import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Search over the whole catalogue, on a phone. */
Item {
    id: root

    function focusSearch() { field.forceActiveFocus() }

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

                    // Debounced: a request per keystroke would hammer the server.
                    onTextChanged: debounce.restart()
                    onAccepted: {
                        debounce.stop()
                        library.search(text)
                        field.focus = false
                    }

                    Timer {
                        id: debounce
                        interval: 320
                        onTriggered: library.search(field.text)
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

        MobileTrackList {
            Layout.fillWidth: true
            Layout.fillHeight: true

            model: library.searchResults
            context: "search"
            emptyText: library.query === "" ? qsTr("Начните печатать, чтобы найти музыку")
                       : library.searching ? qsTr("Ищем…")
                       : qsTr("Ничего не найдено")
        }
    }
}
