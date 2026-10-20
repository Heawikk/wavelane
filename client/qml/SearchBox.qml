import QtQuick
import QtQuick.Controls
import Wavelane

/*!
    A one-line search field that reports what is typed a moment after the last key, so a
    list can narrow itself while the text is being written (letters an input method has
    not committed yet count too).
*/
Item {
    id: root

    property string placeholder: ""
    readonly property string text: field.text

    signal searched(string text)

    function clear() {
        field.text = ""
        debounce.stop()
        root.searched("")
    }

    function emitNow() {
        debounce.stop()
        root.searched((field.text + field.preeditText).trim())
    }

    implicitHeight: Theme.mobileIcons ? 60 : 56

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: Theme.mobileIcons ? 12 : 16
        anchors.rightMargin: Theme.mobileIcons ? 12 : 16
        anchors.topMargin: 10
        anchors.bottomMargin: 10
        color: "transparent"
        border.color: field.activeFocus ? Theme.accent : Theme.borderStrong
        border.width: 1

        Icon {
            x: 12
            anchors.verticalCenter: parent.verticalCenter
            glyph: Theme.iSearch
            font.pixelSize: 15
            color: field.activeFocus ? Theme.text : Theme.faint
        }

        TextField {
            id: field
            anchors.fill: parent
            leftPadding: 38
            rightPadding: 40
            placeholderText: root.placeholder
            color: Theme.text
            placeholderTextColor: Theme.faint
            selectByMouse: true
            font.family: Theme.sans
            font.pixelSize: Theme.mobileIcons ? 16 : 14
            background: null
            inputMethodHints: Qt.ImhNoPredictiveText

            onTextChanged: debounce.restart()
            onPreeditTextChanged: debounce.restart()
            onAccepted: root.emitNow()
            Keys.onEscapePressed: root.clear()

            Timer {
                id: debounce
                interval: 250
                onTriggered: root.emitNow()
            }
        }

        IconButton {
            visible: field.text !== ""
            anchors.right: parent.right
            anchors.rightMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            glyph: Theme.iClose
            glyphSize: 12
            onClicked: root.clear()
        }
    }
}
