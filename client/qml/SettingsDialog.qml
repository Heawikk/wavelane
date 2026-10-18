import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Integrations with the rest of the desktop: what Windows shows in its media
    panel, and what Discord shows on the profile.
*/
Popup {
    id: root

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: 560
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
            title: qsTr("Интеграции")

            IconButton {
                glyph: Theme.iClose
                onClicked: root.close()
            }
        }

        // --- Windows ---
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 18
            Layout.bottomMargin: 6
            spacing: 6

            Mono {
                text: qsTr("Панель мультимедиа Windows")
                color: Theme.text
                font.weight: Font.DemiBold
            }
            Row {
                spacing: 8
                Rectangle {
                    width: 6
                    height: 6
                    radius: 3
                    color: media.active ? Theme.positive : Theme.faint
                    anchors.verticalCenter: parent.verticalCenter
                }
                Mono {
                    text: media.active ? qsTr("Подключена") : qsTr("Недоступна")
                    color: Theme.muted
                }
            }
            Text {
                Layout.fillWidth: true
                text: qsTr("Обложка, название и исполнитель показываются в панели громкости, на экране "
                           + "блокировки и в быстрых настройках. Медиа-клавиши клавиатуры и наушников "
                           + "управляют воспроизведением.")
                color: Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
                lineHeight: 1.2
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: 12
            color: Theme.border
        }

        // --- Discord ---
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true

                Mono {
                    text: qsTr("Discord")
                    color: Theme.text
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                Segmented {
                    options: [
                        { value: "on",  label: qsTr("Включено") },
                        { value: "off", label: qsTr("Выключено") }
                    ]
                    current: app.discordEnabled ? "on" : "off"
                    onPicked: function(value) { app.discordEnabled = value === "on" }
                }
            }

            Row {
                spacing: 8
                Rectangle {
                    width: 6
                    height: 6
                    radius: 3
                    color: discord.connected ? Theme.positive : Theme.faint
                    anchors.verticalCenter: parent.verticalCenter
                }
                Mono {
                    text: discord.status
                    color: discord.connected ? Theme.text : Theme.muted
                    font.capitalization: Font.MixedCase
                    font.letterSpacing: 0.2
                }
            }

            FlatField {
                Layout.fillWidth: true
                label: qsTr("Application ID")
                text: app.discordClientId
                placeholder: "123456789012345678"
                onCommitted: function(value) { app.discordClientId = value }
            }

            FlatField {
                Layout.fillWidth: true
                label: qsTr("Публичный адрес сервера для обложек (необязательно)")
                text: app.discordCoverBase
                placeholder: "https://music.example.com"
                onCommitted: function(value) { app.discordCoverBase = value }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Как подключить: на discord.com/developers/applications создайте приложение с "
                           + "названием «Wavelane» (именно оно покажется в «Слушает Wavelane») и скопируйте "
                           + "его Application ID сюда. Чтобы на профиле было лого, в разделе Rich Presence → "
                           + "Art Assets загрузите client/resources/wavelane-discord.png под именем wavelane.\n\n"
                           + "Обложки треков Discord подтягивает со своих серверов, поэтому они появятся, "
                           + "только если сервер доступен из интернета и адрес указан выше. С сервером на "
                           + "этом же компьютере показывается лого.")
                color: Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
                lineHeight: 1.2
            }
        }
    }
}
