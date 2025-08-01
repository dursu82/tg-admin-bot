#!/usr/bin/env bash

# -e — выйти при любой ошибке команды.
# -u — выйти при обращении к несуществующей переменной.
# -o pipefail — учитывать ошибки в конвейерах.
# Обычно, если команда вроде `grep pattern file | sort`, Bash вернёт код ошибки только последней команды `sort`.
# С pipefail вернётся ненулевой код, если хотя бы одна из команд в пайпе вернёт ошибку.

set -euo pipefail


WG_CONF="/etc/wireguard/wg0.conf"
IPTABLES="/etc/iptables/rules.v4"
IPSETS="/etc/iptables/ipsets"


json_error() {
    echo "$1" >&2
    if [[ $NO_HELP -eq 0 ]]; then
        print_help >&2
    fi
    exit 1
}


print_help() {
    cat << EOF
Использование:
    $0 add --name="Oleg Ivanov" --chainset="oivanov"
    $0 del [--name="Oleg Ivanov"] [--ip=10.100.0.X]
    $0 list
    $0 config [--name="Oleg Ivanov"] [--ip=10.100.0.X] [-u|--update]
    $0 set --name="Oleg Ivanov" [--ip=10.100.0.X] [-a|--add|-r|--remove|-l|--list]

Флаги:
    --no-help   Не показывать справку при ошибках.
EOF
}


check_ip() {
    # Check valid IP
    if [[ $1 =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        local IP=()
        IFS='.' read -r -a IP <<< "$1"
        if ! [[ ${IP[0]} -le 255 && ${IP[1]} -le 255 && ${IP[2]} -le 255 && ${IP[3]} -le 255 ]]; then
            # "Неверный IP-адрес"
            return 1
        fi
    else
        return 1
    fi

    return 0
}


backup_file() {
    local DIR_NAME=$(dirname "$WG_CONF")
    mkdir -p "${DIR_NAME}/BACKUP/"

    cp $WG_CONF "${DIR_NAME}/BACKUP/$(basename $WG_CONF)-$(date +%d-%m-%Y-%s)"
    cp $IPTABLES "${DIR_NAME}/BACKUP/$(basename $IPTABLES)-$(date +%d-%m-%Y-%s)"
    cp $IPSETS "${DIR_NAME}/BACKUP/$(basename $IPSETS)-$(date +%d-%m-%Y-%s)"
}


generate_keys() {
    PRIVATE_KEY=$(wg genkey)
    PUBLIC_KEY=$(echo "$PRIVATE_KEY" | wg pubkey)
    PSK_KEY=$(wg genpsk)
}


check_wg() {
    local arr=()
    local name=$(echo $1 | tr -d ' \t' | tr '[:upper:]' '[:lower:]' | grep -o . | sort | tr -d '\n')


    while read -r line; do
        arr+=($(echo $line | grep -o . | sort | tr -d '\n'))
    done < <(grep "\-WG- Peer:" "$WG_CONF" | cut -d: -f2 | tr -d ' \t' | grep -v '^$' | tr '[:upper:]' '[:lower:]')


    # * - Склеивает всё в одну строку с разделителем IFS
    # @ - Раскрывает каждый элемент отдельно. Каждый элемент массива остаётся отдельной строкой при раскрытии.
    if [[ " ${arr[*]} " =~ " $name " ]]; then
        return 0
    else
        return 1
    fi
}


check_iptables() {
    local arr=()


    while read -r line; do
        arr+=( $line )
    done < <(grep "^-N" "$IPTABLES" | cut -d' ' -f2 | tr -d ' \t' | grep -v '^$' | tr '[:upper:]' '[:lower:]')


    if [[ "${arr[@]}" == *"$1"* ]]; then
        # Найдено
        return 0
    else
        return 1
    fi
}


check_ipsets() {
    # Проверить, ipset и ipset-save должны быть одинаковыми
    local active_sets=$(ipset list -n | sort | tr '\n' ' ')
    local saved_sets=$(grep '^create' "$IPSETS" | awk '{print $2}' | sort | tr '\n' ' ')

    if [[ "$active_sets" != "$saved_sets" ]]; then
        # Списки сетов не совпадают
        return 1
    elif [[ "$1" == "--check-only-sets" ]]; then
        return 0
    fi


    if [[ "$active_sets" == *"$1"* ]]; then
        # Найдено
        return 0
    else
        return 1
    fi
}


main_add() {
    if check_wg "$1"; then
        json_error "WG: Peer с таким именем уже существует."
    fi

    if check_iptables "$2"; then
        json_error "Iptables: Chain с таким именем уже существует."
    fi

    if check_ipsets "$2"; then
        json_error "Ipsets: Set с таким именем уже существует."
    fi

    backup_file

    # --
    # generate_new_ip
    local arr=($(grep AllowedIPs $WG_CONF | awk '{print $3}' | sed 's/\/.*//' | cut -d. -f4 | awk '$1 > 10' | sort -n))
    local new=$((${arr[-1]} + 1))

    for ((i = 1; i < ${#arr[@]}; i++)); do
        local last=${arr[i-1]}
        local next=${arr[i]}
        if ((next != last + 1)); then
            new=$((last + 1))
            break
        fi
    done
    # --

    generate_keys

    # --
    # update_wg_conf
    WG_CONF_TEMP=$(mktemp)

    #/^\[Peer\]/ { in_block=0}
    awk -v new_ip="10.100.0.$new" -v last_ip="10.100.0.$(($new - 1))" -v name="$1" -v PRIVATE_KEY=$PRIVATE_KEY -v PUBLIC_KEY=$PUBLIC_KEY -v PSK_KEY=$PSK_KEY '
    /AllowedIPs/ {
        if ($0 ~  last_ip) {
            in_block=1
        }
    }
    {
        print $0
        if (in_block && /PersistentKeepalive/) {
            print ""
            print ""
            print "# -WG- Peer: " name
            print "# -WG- PrivateKey: " PRIVATE_KEY
            print "[Peer]"
            print "PublicKey = " PUBLIC_KEY
            print "PresharedKey = " PSK_KEY
            print "AllowedIPs = " new_ip "/32"
            print "PersistentKeepalive = 16"
            in_block=0
        }
    }' "$WG_CONF" > "$WG_CONF_TEMP"
    mv --force "$WG_CONF_TEMP" "$WG_CONF"
    # --

    # --
    # update_iptables
    IPTABLES_TEMP=$(mktemp)

    awk -v new_ip="10.100.0.$new" -v last_ip="10.100.0.$(($new - 1))" -v name="$1" -v chainset="$2" '
    /^-N/ { last_n = NR }
    { lines[NR] = $0 }
    END {
        in_filter = 0
        for (i = 1; i <= NR; i++) {
            line = lines[i]

            if (line ~ /^\*filter$/) in_filter = 1
            else if (line ~ /^\*/ && line != "*filter") in_filter = 0

            if (i == last_n) {
                print line
                print "-N " chainset
                continue
            }

            if (in_filter && line ~ /^COMMIT$/) {
                print "-A " chainset " -m set --match-set " chainset "_dst dst -j ACCEPT -m comment --comment \"" name "\""
            }

            print line

            if (line ~ ("-A FORWARD -i wg0 -s " last_ip)) {
                print "-A FORWARD -i wg0 -s " new_ip " -j " chainset
            }
        }
    }' "$IPTABLES" > "$IPTABLES_TEMP"
    mv --force "$IPTABLES_TEMP" "$IPTABLES"
    # --

    # --
    # update_ipsets
    ipset create "$2_dst" hash:ip
    ipset save "$2_dst" | grep "^create" >> "$IPSETS"
    # --

    # Еше раз проверяем, что после добавления нового set - всё в порядке
    if ! check_ipsets --check-only-sets; then
        json_error "Ipsets: Sets отличаются."
        # Откатить назад ?
    fi

    iptables-restore "$IPTABLES"
    wg syncconf wg0 <(wg-quick strip wg0)

    echo "{\"Peer\": \"$1\", \"PrivateKey\": \"$PRIVATE_KEY\",\"PresharedKey\": \"$PSK_KEY\",\"ip\": \"10.100.0.$new\"}"
}


main_del() {
    if [[ -n "$1" ]]; then
        if ! check_wg "$1"; then
            json_error "WG: Peer с таким именем не существует."
        fi
        local chainset=$(grep -F "$1" "$IPTABLES" | awk '{print $2}')
    elif [[ -n "$2" ]]; then
        # Передан только IP
        if ! grep -qE "^[[:space:]]*AllowedIPs[[:space:]]*=[[:space:]]*$2(/[0-9]+)?" "$WG_CONF"; then
            json_error "WG: Peer с таким IP не существует."
        fi
        local chainset=$(grep -F "$2" "$IPTABLES" | awk '{print $8}')
    else
        json_error "Для команды del не указаны параметры."
    fi

    backup_file
    WG_CONF_TEMP=$(mktemp)

    awk -v name="$1" -v ip="$2" '
    BEGIN { RS=""; ORS="\n\n\n" }
    {
        # Найти строку с AllowedIPs
        match($0, /AllowedIPs[[:space:]]*=[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+)\.([0-9]+)/, arr)

        if (arr[2] && arr[2] > 0 && arr[2] <= 10) {
            print $0
        } else if ((name && $0 !~ name) || (!name && ip && $0 !~ ip)) {
            print $0
        }
    }
    ' "$WG_CONF" > "$WG_CONF_TEMP"
    mv  --force "$WG_CONF_TEMP" "$WG_CONF"


    # Удалить из iptables
    #-A ttest -m set --match-set ttest_dst dst -j ACCEPT  -m comment --comment "Test Test"
    #-A FORWARD -i wg0 -s 10.100.0.99 -j ttest
    sed -i "/$chainset/d" $IPTABLES

    iptables-restore "$IPTABLES"
    wg syncconf wg0 <(wg-quick strip wg0)

    # Удалить из ipsets
    ipset destroy "${chainset}_dst"
    sed -i "/$chainset/d" $IPSETS
    echo  "{\"success\":true}"
}


main_list() {
    awk '
    BEGIN {
        print "["
        comma = 0
    }
    /# -WG- Peer:/ {
        name=$4" "$5
    }
    /AllowedIPs/ {
        split($3, ip, "/")
        split(ip[1],bytes,".")
        if (bytes[4] > 10) {
            if (comma) {
                print ","
            }
            printf "  {\"name\": \"%s\", \"ip\": \"%s\"}", name, ip[1]
            comma = 1
        }
    }
    END {
        print "\n]"
    }' $WG_CONF
}


main_config() {

    config_show() {

        awk -v name="$1" -v ip="$2" -v PublicKey="$(grep '\-WG- PublicKey' $WG_CONF | awk '{print $5}')" '
        BEGIN { RS=""; FS="\n"}
        {
            peer_name = ""
            PrivateKey = ""
            PresharedKey = ""
            peer_ip = ""

            for (i = 1; i <= NF; i++) {
                if ($i ~ /-WG- Peer/) {
                    sub(/^[^:]*:[[:space:]]*/, "", $i)
                    peer_name = $i
                }
                if ($i ~ /-WG- PrivateKey/) {
                    sub(/^[^:]*:[[:space:]]*/, "", $i)
                    PrivateKey = $i
                }
                if ($i ~ /PresharedKey/) {
                    sub(/^[^=]*=[[:space:]]*/, "", $i)
                    PresharedKey = $i
                }
                if ($i ~ /AllowedIPs/) {
                    match($i, /AllowedIPs[[:space:]]*=[[:space:]]*([0-9\.\/]+)/, arr)
                    peer_ip = arr[1]
                    sub(/\/.*/, "", peer_ip) # убираем маску
                }
            }

            split(peer_ip,bytes,".")

            # фильтрация по имени или IP
            if (bytes[4] > 10 && ((name && peer_name == name) || (!name && ip && peer_ip == ip))) {
                printf("{\"Peer\": \"%s\",\"PrivateKey\": \"%s\",\"PresharedKey\": \"%s\",\"ip\": \"%s\"}\n",
                    peer_name, PrivateKey, PresharedKey, peer_ip)
            }
        }' $WG_CONF
    }

    if [[ $3 == "update" ]]; then
        read -r PrivateKey PresharedKey < <(config_show "$1" "$2" | jq -r '"\(.PrivateKey) \(.PresharedKey)"')
        PublicKey=$(echo "$PrivateKey" | wg pubkey)
        generate_keys
        backup_file
        sed -i \
            -e "s|$PrivateKey|$PRIVATE_KEY|" \
            -e "s|$PublicKey|$PUBLIC_KEY|" \
            -e "s|$PresharedKey|$PSK_KEY|" \
            $WG_CONF
        wg syncconf wg0 <(wg-quick strip wg0)
    fi
    config_show "$1" "$2"
}


main_set() {
    if ! check_wg "$1"; then
        json_error "WG: Peer с таким именем не существует."
    fi

    local chainset=$(grep -F "$1" "$IPTABLES" | awk '{print $2}')

    if ! check_ipsets "$chainset"; then
        json_error "Ipsets: Set с таким именем '$chainset' не существует."
    fi

    case $3 in
        add)
            # Проверим, есть ли такой IP
            if grep -q "^add ${chainset}_dst $2" "$IPSETS"; then
                json_error "Ipsets: такой ip '$2' уже существует."
            fi
            backup_file
            if grep -qE "^add ${chainset}_dst" $IPSETS; then
                ip_list=$(grep "^add ${chainset}_dst" $IPSETS | awk -v chainset="${chainset}_dst" -v ip="$2" '{print} END {print "add " chainset " " ip}' | sort -t' ' -k3,3V)
            else
                ip_list="add ${chainset}_dst $2"
            fi
            IPSETS_TEMP=$(mktemp)
            grep -v "^add ${chainset}_dst" "$IPSETS" > "$IPSETS_TEMP"
            line_num=$(grep -n "^create ${chainset}_dst" "$IPSETS_TEMP" | cut -d: -f1)
            awk -v line_num="$line_num" -v ip_list="${ip_list[@]}" 'NR==line_num {print; print ip_list; next}1' "$IPSETS_TEMP" > "$IPSETS"
            rm "$IPSETS_TEMP"
            ipset add "${chainset}_dst" "$2"
            echo  "{\"success\":true}"
            ;;
        remove)
            # Проверим, есть ли такой IP
            if ! grep -q "^add ${chainset}_dst $2" "$IPSETS"; then
                json_error "Ipsets: такого ip '$2' нет."
            fi
            backup_file
            sed -i "/add ${chainset}_dst $2/d" $IPSETS
            ipset del "${chainset}_dst" "$2"
            echo  "{\"success\":true}"
            ;;
        list)
            grep "^add ${chainset}_dst" $IPSETS | awk '
            BEGIN {
                print "["
                comma = 0
            }
            {
                if (comma) {
                    print ","
                }
                printf "  \"%s\"", $3
                comma = 1
            }
            END {
                print "\n]"
            }'
            ;;
    esac
}


NO_HELP=0

# Предварительно проверим глобальные флаги
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --no-help)
            NO_HELP=1
            ;;
        *)
            ARGS+=("$arg")
            ;;
    esac
done
set -- "${ARGS[@]}"

if [[ $# -lt 1 ]]; then
    json_error "Не указана команда."
fi

COMMAND=$1
shift

case "$COMMAND" in
    add)
        NAME=""
        CHAINSET=""

        for arg in "$@"; do
            case $arg in
                --name=*)
                    if [[ -n "$NAME" ]]; then
                        json_error "Ошибка: параметр --name уже был указан!"
                    fi
                    NAME="${arg#*=}"
                    ;;
                --chainset=*)
                    if [[ -n "$CHAINSET" ]]; then
                        json_error "Ошибка: параметр --chainset уже был указан!"
                    fi
                    CHAINSET="${arg#*=}"
                    ;;
                *)
                    json_error "Неизвестный параметр для add: $arg"
                    ;;
            esac
        done

        if [[ -z "$NAME" || -z "$CHAINSET" ]]; then
            json_error "Для команды add нужны параметры --name и --chainset."
        fi

        if [[ $(wc -w <<< "$NAME") -ne 2 ]]; then
            json_error "Параметр --name должен содержать ровно два слова."
        fi

        if ! [[ "$CHAINSET" =~ ^[a-zA-Z0-9_]+$ ]]; then
            json_error "Параметр --chain должен содержать одно слово из букв, цифр и подчёркиваний."
        fi

        main_add "$NAME" "$CHAINSET"
        ;;

    list)
        if [ $# -ne 0 ]; then
            json_error "Команда list не принимает параметры."
        fi

        main_list
        ;;

    config)
        NAME=""
        IP=""
        ACTION=""

        for arg in "$@"; do
            case $arg in
                --name=*)
                    if [[ -n "$NAME" ]]; then
                        json_error "Ошибка: параметр --name уже был указан!"
                    fi
                    NAME="${arg#*=}"
                    ;;
                --ip=*)
                    if [[ -n "$IP" ]]; then
                        json_error "Ошибка: Параметр --ip уже был указан!"
                    fi
                    IP="${arg#*=}"
                    ;;
                -u|--update)
                    if [[ -n "$ACTION" ]]; then
                        json_error "Ошибка: флаг -u уже был указан!"
                    fi
                    ACTION="update"
                    ;;

            *)
                json_error "Неизвестный параметр для config: $arg"
                ;;
            esac
        done

        # Если заданы и --name, и --ip, то используется только --name
        if [[ -z "$NAME" && -z "$IP" ]]; then
            json_error "Для команды config нужны параметры --name или --ip."
        elif [[ -z "$NAME" ]] && ! check_ip "$IP"; then
            json_error "Неверный IP-адрес"
        fi

        main_config "$NAME" "$IP" "$ACTION"
        ;;

    del)
        NAME=""
        IP=""

        for arg in "$@"; do
            case $arg in
                --name=*)
                    if [[ -n "$NAME" ]]; then
                        json_error "Ошибка: параметр --name уже был указан!"
                    fi
                    NAME="${arg#*=}"
                    ;;
                --ip=*)
                    if [[ -n "$IP" ]]; then
                        json_error "Ошибка: Параметр --ip уже был указан!"
                    fi
                    IP="${arg#*=}"
                    ;;
            *)
                json_error "Неизвестный параметр для del: $arg"
                ;;
            esac
        done

        # Если заданы и --name, и --ip, то используется только --name
        if [[ -z "$NAME" && -z "$IP" ]]; then
            json_error "Для команды del нужны параметры --name или --ip."
        elif [[ -n "$NAME" && $(wc -w <<< "$NAME") -ne 2 ]]; then
            json_error "Параметр --name должен содержать ровно два слова."
        elif [[ -n "$IP" ]] && ! check_ip "$IP"; then
            json_error "Неверный IP-адрес"
        fi

        main_del "$NAME" "$IP"
        ;;

    set)
        NAME=""
        IP=""
        ACTION=""

        for arg in "$@"; do
            case $arg in
                --name=*)
                    if [[ -n "$NAME" ]]; then
                        json_error "Ошибка: параметр --name уже был указан!"
                    fi
                    NAME="${arg#*=}"
                    ;;
                --ip=*)
                    if [[ -n "$IP" ]]; then
                        json_error "Ошибка: Параметр --ip уже был указан!"
                    fi
                    IP="${arg#*=}"
                    ;;
                -a|--add)
                    if [[ -n "$ACTION" ]]; then
                        json_error "Ошибка: флаг -a, -r или -l уже был указан!"
                    fi
                    ACTION="add"
                    ;;
                -r|--remove)
                    if [[ -n "$ACTION" ]]; then
                        json_error "Ошибка: флаг -a, -r или -l уже был указан!"
                    fi
                    ACTION="remove"
                    ;;
                -l|--list)
                    if [[ -n "$ACTION" ]]; then
                        json_error "Ошибка: флаг -a, -r или -l уже был указан!"
                    fi
                    ACTION="list"
                    ;;
            *)
                json_error "Неизвестный параметр для config: $arg"
                ;;
            esac
        done

        if [[ ( -z "$NAME" || -z "$IP" || -z "$ACTION" ) && "$ACTION" != "list" ]]; then
            json_error "Не указаны обязательные параметры: --name --ip -a/-r/-l."
        elif [[ $(wc -w <<< "$NAME") -ne 2 ]]; then
            json_error "Параметр --name должен содержать ровно два слова."
        elif [[ "$ACTION" != "list" ]] && ! check_ip "$IP"; then
            json_error "Неверный IP-адрес"
        fi

        main_set "$NAME" "$IP" "$ACTION"
        ;;

    *)
        json_error "Неизвестная команда: $COMMAND"
        ;;
esac
