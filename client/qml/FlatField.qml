import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! A labelled, square text field that reports its value when editing ends. */
ColumnLayout {
    id: root

    property string label: ""
    property string text: ""
    property string placeholder: ""
    //! What is in the field right now (as opposed to `text`, which is only where it starts).
    property alias inputText: input.text
    property alias validator: input.validator
    property alias maxLength: input.maximumLength

    signal committed(string value)

    spacing: 5

    Mono {
        text: root.label
        font.pixelSize: 10
        color: Theme.faint
    }

    TextField {
        id: input
        Layout.fillWidth: true
        implicitHeight: 32
        leftPadding: 10
        rightPadding: 10
        text: root.text
        placeholderText: root.placeholder
        color: Theme.text
        placeholderTextColor: Theme.faint
        selectByMouse: true
        font.family: Theme.sans
        font.pixelSize: Theme.fontSmall
        onEditingFinished: root.committed(text)

        background: Rectangle {
            color: Theme.panel
            border.color: input.activeFocus ? Theme.accent : Theme.borderStrong
            border.width: 1
        }
    }
}
