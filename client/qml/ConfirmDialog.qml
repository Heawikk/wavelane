import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! A small modal "are you sure?", in the same flat style as everything else. */
Popup {
    id: root

    property string heading: ""
    property string message: ""
    property string confirmText: qsTr("Подтвердить")
    property bool danger: false

    signal accepted()

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: 440
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    contentItem: ColumnLayout {
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: root.heading
        }

        Text {
            Layout.fillWidth: true
            Layout.margins: 20
            Layout.bottomMargin: 8
            text: root.message
            color: Theme.muted
            font.family: Theme.sans
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            lineHeight: 1.25
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 20
            Layout.topMargin: 12
            spacing: 8

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTr("Отмена")
                onClicked: root.close()
            }
            FlatButton {
                text: root.confirmText
                primary: !root.danger
                danger: root.danger
                onClicked: {
                    root.close()
                    root.accepted()
                }
            }
        }
    }
}
