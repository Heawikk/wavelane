import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Full-catalogue search. */
Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLarge
        spacing: Theme.spacing

        Text {
            text: qsTr("Поиск")
            color: Theme.text
            font.pixelSize: Theme.fontHeading
            font.weight: Font.Bold
        }

        TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: qsTr("Трек, исполнитель или альбом")
            color: Theme.text
            placeholderTextColor: Theme.textFaint
            selectByMouse: true
            font.pixelSize: Theme.fontBody

            background: Rectangle {
                implicitHeight: 42
                radius: Theme.radiusSmall
                color: Theme.surface
                border.color: searchField.activeFocus ? Theme.accent : Theme.border
                border.width: 1
            }

            // Debounced: a request per keystroke would hammer the server and
            // the answers could arrive out of order.
            onTextChanged: debounce.restart()
            Keys.onReturnPressed: {
                debounce.stop()
                library.search(text)
            }

            Timer {
                id: debounce
                interval: 280
                onTriggered: library.search(searchField.text)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                visible: library.query !== "" && !library.searching
                text: library.searchResults.count > 0
                      ? qsTr("Найдено: %1").arg(library.searchResults.count)
                      : qsTr("Ничего не найдено")
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
            }

            BusyIndicator {
                running: library.searching
                visible: running
                implicitWidth: 20
                implicitHeight: 20
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: library.searchResults.count > 0
                text: qsTr("Двойной клик — слушать")
                color: Theme.textFaint
                font.pixelSize: Theme.fontTiny
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: library.searchResults
            clip: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {}

            delegate: TrackRow {
                required property int index
                width: ListView.view.width
                onActivated: library.playFrom(library.searchResults, index, "search")
            }

            // Shown over the empty list rather than as another layout item,
            // which would compete with the list for the available height.
            Text {
                anchors.centerIn: parent
                width: parent.width * 0.7
                visible: library.query === "" && !library.searching
                text: qsTr("Начните печатать, чтобы найти музыку")
                color: Theme.textFaint
                font.pixelSize: Theme.fontBody
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }
}
