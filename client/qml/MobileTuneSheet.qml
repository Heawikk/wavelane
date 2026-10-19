import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! The wave's dials (what to listen to, mood, language, variety) in a sheet from the bottom. */
Popup {
    id: root

    parent: Overlay.overlay
    x: 0
    y: parent.height - height
    width: parent.width
    modal: true
    dim: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    readonly property var characterOptions: [
        { value: "any",        label: qsTr("Любой") },
        { value: "favourite",  label: qsTr("Любимое") },
        { value: "unfamiliar", label: qsTr("Новое") },
        { value: "popular",    label: qsTr("Хиты") }
    ]
    readonly property var moodOptions: [
        { value: "any",       label: qsTr("Любое") },
        { value: "energetic", label: qsTr("Бодрое") },
        { value: "party",     label: qsTr("Танцевальное") },
        { value: "chill",     label: qsTr("Спокойное") },
        { value: "calm",      label: qsTr("Тихое") },
        { value: "focus",     label: qsTr("Для сосредоточения") },
        { value: "sad",       label: qsTr("Грустное") }
    ]
    readonly property var languageOptions: [
        { value: "any",          label: qsTr("Любой") },
        { value: "russian",      label: qsTr("Русский") },
        { value: "foreign",      label: qsTr("Иностранный") },
        { value: "instrumental", label: qsTr("Без слов") }
    ]
    readonly property var diversityOptions: [
        { value: "0.1", label: "10%" },
        { value: "0.3", label: "30%" },
        { value: "0.6", label: "60%" },
        { value: "0.9", label: "90%" }
    ]

    //! The stored variety is a free number; show the nearest preset.
    function nearestDiversity() {
        let best = diversityOptions[0].value
        let distance = 10
        for (let i = 0; i < diversityOptions.length; ++i) {
            const gap = Math.abs(parseFloat(diversityOptions[i].value) - wave.diversity)
            if (gap < distance) {
                distance = gap
                best = diversityOptions[i].value
            }
        }
        return best
    }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    contentItem: ColumnLayout {
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Настроить волну")

            IconButton {
                glyph: Theme.iClose
                onClicked: root.close()
            }
        }

        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(dials.implicitHeight + 24,
                                             (root.parent ? root.parent.height : 800) * 0.7)
            contentHeight: dials.implicitHeight + 24
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: dials
                x: 16
                y: 12
                width: parent.width - 32
                spacing: 14

                component Group: ColumnLayout {
                    property string heading: ""
                    property var options: []
                    property string current: ""
                    signal picked(string value)

                    Layout.fillWidth: true
                    spacing: 8

                    Mono { text: parent.heading; color: Theme.faint }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8

                        Repeater {
                            model: parent.parent.options
                            delegate: Chip {
                                required property var modelData
                                label: modelData.label
                                on: modelData.value === parent.parent.current
                                onClicked: parent.parent.picked(modelData.value)
                            }
                        }
                    }
                }

                Group {
                    heading: qsTr("Что слушать")
                    options: root.characterOptions
                    current: wave.character
                    onPicked: function(value) { wave.setCharacter(value) }
                }
                Group {
                    heading: qsTr("Настроение")
                    options: root.moodOptions
                    current: wave.mood
                    onPicked: function(value) { wave.setMood(value) }
                }
                Group {
                    heading: qsTr("Язык")
                    options: root.languageOptions
                    current: wave.language
                    onPicked: function(value) { wave.setLanguage(value) }
                }
                Group {
                    heading: qsTr("Разнообразие")
                    options: root.diversityOptions
                    current: root.nearestDiversity()
                    onPicked: function(value) { wave.setDiversity(parseFloat(value)) }
                }
            }
        }
    }
}
