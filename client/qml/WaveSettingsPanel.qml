import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Mood, character and language — the three dials of the wave.

    They map one-to-one onto the server's WaveSettings; mood narrows which
    tracks may play at all, while character shifts how familiar they should be.
*/
Rectangle {
    id: root

    implicitHeight: content.implicitHeight + 2 * Theme.spacingLarge
    radius: Theme.radius
    color: Theme.surface
    border.color: Theme.border
    border.width: 1

    readonly property var moods: [
        { value: "any",       label: qsTr("Любое") },
        { value: "energetic", label: qsTr("Бодрое") },
        { value: "party",     label: qsTr("Танцевальное") },
        { value: "chill",     label: qsTr("Спокойное") },
        { value: "calm",      label: qsTr("Тихое") },
        { value: "focus",     label: qsTr("Для сосредоточения") },
        { value: "sad",       label: qsTr("Грустное") }
    ]

    readonly property var characters: [
        { value: "any",        label: qsTr("Любой") },
        { value: "favourite",  label: qsTr("Любимое") },
        { value: "unfamiliar", label: qsTr("Незнакомое") },
        { value: "popular",    label: qsTr("Популярное") }
    ]

    readonly property var languages: [
        { value: "any",          label: qsTr("Любой") },
        { value: "russian",      label: qsTr("Русский") },
        { value: "foreign",      label: qsTr("Иностранный") },
        { value: "instrumental", label: qsTr("Без слов") }
    ]

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.spacingLarge
        spacing: Theme.spacing

        ChipGroup {
            Layout.fillWidth: true
            label: qsTr("Настроение")
            options: root.moods
            current: wave.mood
            onPicked: function(value) { wave.setMood(value) }
        }

        ChipGroup {
            Layout.fillWidth: true
            label: qsTr("Характер")
            options: root.characters
            current: wave.character
            onPicked: function(value) { wave.setCharacter(value) }
        }

        ChipGroup {
            Layout.fillWidth: true
            label: qsTr("Язык")
            options: root.languages
            current: wave.language
            onPicked: function(value) { wave.setLanguage(value) }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: qsTr("Разнообразие")
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: Math.round(wave.diversity * 100) + "%"
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontTiny
                }
            }

            Slider {
                id: diversitySlider
                Layout.fillWidth: true
                from: 0.0
                to: 1.0
                value: wave.diversity
                // Only commit when the drag ends, so one gesture is one request.
                onPressedChanged: {
                    if (!pressed)
                        wave.setDiversity(value)
                }

                background: Rectangle {
                    x: diversitySlider.leftPadding
                    y: diversitySlider.topPadding + diversitySlider.availableHeight / 2 - 2
                    width: diversitySlider.availableWidth
                    height: 4
                    radius: 2
                    color: Theme.surfaceActive

                    Rectangle {
                        width: diversitySlider.visualPosition * parent.width
                        height: parent.height
                        radius: 2
                        color: Theme.accent
                    }
                }

                handle: Rectangle {
                    x: diversitySlider.leftPadding
                       + diversitySlider.visualPosition * (diversitySlider.availableWidth - width)
                    y: diversitySlider.topPadding + diversitySlider.availableHeight / 2 - height / 2
                    width: 14
                    height: 14
                    radius: 7
                    color: Theme.text
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Слева — ближе к привычному, справа — больше неожиданного")
                color: Theme.textFaint
                font.pixelSize: Theme.fontTiny
                wrapMode: Text.WordWrap
            }
        }
    }

    // --- a labelled row of selectable chips ---
    component ChipGroup: ColumnLayout {
        id: group

        property string label: ""
        property var options: []
        property string current: ""

        signal picked(string value)

        spacing: 6

        Text {
            text: group.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontTiny
        }

        Flow {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: group.options

                delegate: Rectangle {
                    required property var modelData
                    readonly property bool selected: group.current === modelData.value

                    height: 30
                    width: chipLabel.implicitWidth + 26
                    radius: 15
                    color: selected ? Theme.accent
                                    : (chipMouse.containsMouse ? Theme.surfaceActive
                                                               : Theme.surfaceHover)

                    Behavior on color {
                        ColorAnimation { duration: Theme.durationFast }
                    }

                    Text {
                        id: chipLabel
                        anchors.centerIn: parent
                        text: modelData.label
                        color: parent.selected ? "white" : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.weight: parent.selected ? Font.DemiBold : Font.Normal
                    }

                    MouseArea {
                        id: chipMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: group.picked(modelData.value)
                    }
                }
            }
        }
    }
}
