import QtQuick
import QtQuick.Controls
import Wavelane

/*! A flat drop-down over a list of { value, label } options. */
ComboBox {
    id: control

    property var options: []
    property string current: ""

    signal picked(string value)

    function indexFor(value) {
        for (let i = 0; i < options.length; ++i) {
            if (options[i].value === value)
                return i
        }
        return -1
    }

    model: options
    textRole: "label"
    currentIndex: indexFor(current)
    onActivated: function(index) { control.picked(options[index].value) }

    implicitWidth: 180
    implicitHeight: 28

    contentItem: Mono {
        leftPadding: 10
        rightPadding: 26
        text: control.displayText
        color: Theme.text
        font.capitalization: Font.MixedCase
        font.letterSpacing: 0.2
        font.pixelSize: Theme.fontSmall
    }

    indicator: Icon {
        x: control.width - width - 8
        y: (control.height - height) / 2
        glyph: Theme.iChevronDown
        font.pixelSize: 10
    }

    background: Rectangle {
        color: "transparent"
        border.color: control.popup.visible || control.hovered ? Theme.faint : Theme.borderStrong
        border.width: 1
    }

    delegate: ItemDelegate {
        id: item

        required property var modelData
        required property int index

        width: control.width
        height: 28
        highlighted: control.highlightedIndex === index

        contentItem: Mono {
            leftPadding: 4
            text: item.modelData.label
            color: item.modelData.value === control.current ? Theme.accentText : Theme.text
            font.capitalization: Font.MixedCase
            font.letterSpacing: 0.2
            font.pixelSize: Theme.fontSmall
        }
        background: Rectangle {
            color: item.highlighted ? Theme.rowSelected : "transparent"
        }
    }

    popup: Popup {
        y: control.height - 1
        width: control.width
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }
        background: Rectangle {
            color: Theme.bar
            border.color: Theme.borderStrong
            border.width: 1
        }
    }
}
