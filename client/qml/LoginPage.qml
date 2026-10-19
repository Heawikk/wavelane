import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Sign-in and registration, in the same flat style as the workspace. */
Item {
    id: root

    property bool registering: false

    function submit() {
        auth.setServerUrl(serverField.text)
        if (root.registering)
            auth.signUp(emailField.text, loginField.text, passwordField.text, "")
        else
            auth.signIn(loginField.text, passwordField.text)
    }

    // one labelled, square input
    component Field: ColumnLayout {
        id: field

        property alias text: input.text
        property alias placeholder: input.placeholderText
        property alias echoMode: input.echoMode
        property string label: ""

        signal accepted()

        Layout.fillWidth: true
        spacing: 5

        Mono {
            text: field.label
            font.pixelSize: 10
            color: Theme.faint
        }

        TextField {
            id: input
            Layout.fillWidth: true
            implicitHeight: 34
            leftPadding: 10
            rightPadding: 10
            color: Theme.text
            placeholderTextColor: Theme.faint
            selectByMouse: true
            font.family: Theme.sans
            font.pixelSize: Theme.fontBody
            Keys.onReturnPressed: field.accepted()

            background: Rectangle {
                color: Theme.panel
                border.color: input.activeFocus ? Theme.accent : Theme.borderStrong
                border.width: 1
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(380, root.width - 32)
        height: form.implicitHeight + 2 * 24
        color: Theme.panel
        border.color: Theme.border
        border.width: 1

        ColumnLayout {
            id: form
            anchors.fill: parent
            anchors.margins: 24
            spacing: 14

            RowLayout {
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 16
                    color: Theme.accent

                    Mono {
                        anchors.centerIn: parent
                        text: root.registering ? "02" : "01"
                        color: "white"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                }
                Mono {
                    text: root.registering ? qsTr("Создать аккаунт") : qsTr("Вход")
                    color: Theme.text
                    font.weight: Font.DemiBold
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Ваша музыка. Ваша волна.")
                color: Theme.muted
                font.family: Theme.sans
                font.pixelSize: Theme.fontTitle
                font.weight: Font.Bold
            }

            Field {
                id: serverField
                label: qsTr("Сервер")
                text: app.serverUrl
                placeholder: "http://127.0.0.1:8000"
                onAccepted: root.submit()
            }

            Field {
                id: emailField
                visible: root.registering
                label: qsTr("Электронная почта")
                onAccepted: root.submit()
            }

            Field {
                id: loginField
                label: root.registering ? qsTr("Имя пользователя") : qsTr("Имя пользователя или почта")
                text: root.registering ? "" : auth.lastLogin
                onAccepted: root.submit()
            }

            Field {
                id: passwordField
                label: qsTr("Пароль")
                echoMode: TextInput.Password
                onAccepted: root.submit()
            }

            Text {
                Layout.fillWidth: true
                visible: auth.errorMessage !== ""
                text: auth.errorMessage
                color: Theme.negative
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }

            FlatButton {
                Layout.fillWidth: true
                primary: true
                implicitHeight: 36
                text: auth.busy ? qsTr("Подождите…")
                                : (root.registering ? qsTr("Создать аккаунт") : qsTr("Войти"))
                enabledWhen: !auth.busy
                onClicked: root.submit()
            }

            Mono {
                Layout.alignment: Qt.AlignHCenter
                text: root.registering ? qsTr("Уже есть аккаунт? Войти")
                                       : qsTr("Нет аккаунта? Зарегистрироваться")
                color: Theme.accentText

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.registering = !root.registering
                        auth.clearError()
                    }
                }
            }

            Mono {
                Layout.fillWidth: true
                visible: root.registering
                text: qsTr("Первый зарегистрированный аккаунт становится администратором сервера.")
                font.capitalization: Font.MixedCase
                font.letterSpacing: 0.2
                font.pixelSize: 10
                color: Theme.faint
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
            }
        }
    }
}
