/**
 * SPECTRA Edge Node - STM32F407 Firmware Taslağı
 *
 * bu dosya tam firmware değil, mantık şablonudur.
 * STM32CubeIDE'de proje oluşturulup bu mantık entegre edilir.
 *
 * donanım bağlantıları:
 *   - LM35  → PA0 (ADC1_CH0)  → sıcaklık
 *   - LDR   → PA1 (ADC1_CH1)  → ışık
 *   - POT   → PA4 (ADC1_CH4)  → potansiyometre
 *   - HC-SR04 TRIG → PB6      → ultrasonik mesafe
 *   - HC-SR04 ECHO → PB7      → ultrasonik mesafe
 *   - OLED SDA → PB9 (I2C1)   → ekran
 *   - OLED SCL → PB8 (I2C1)   → ekran
 *   - BUZZER → PA5             → ses
 *   - UART TX → PA2 (USART2)  → PC iletişim
 *   - UART RX → PA3 (USART2)  → PC iletişim
 */

#include "main.h"
#include "string.h"
#include "stdio.h"

/* ========== PROTOKOL SABITLERI ========== */
#define START_BYTE  0xAA
#define END_BYTE    0x55
#define MAX_DATA    255

/* komut kodları (Python tarafıyla aynı) */
#define CMD_SET_MODE        0x01
#define CMD_REQUEST_STATUS  0x02
#define CMD_SET_ALERT       0x03
#define CMD_DISPLAY_TEXT    0x04
#define CMD_BUZZER_ON       0x05
#define CMD_BUZZER_OFF      0x06
#define CMD_STATUS_REPORT   0x10
#define CMD_SENSOR_DATA     0x11
#define CMD_MODE_ACK        0x12
#define CMD_HEARTBEAT       0x13
#define CMD_ALERT           0x14

/* ========== DURUM DEĞİŞKENLERİ ========== */
typedef enum {
    MODE_NORMAL = 0,
    MODE_DEGRADED = 1,
    MODE_LOCAL_AUTONOMY = 2,
    MODE_SILENT = 3,
    MODE_EMERGENCY = 4,
} NodeMode;

typedef enum {
    ALERT_NONE = 0,
    ALERT_LOW = 1,
    ALERT_MEDIUM = 2,
    ALERT_HIGH = 3,
    ALERT_CRITICAL = 4,
} AlertLevel;

/* global durum */
volatile NodeMode current_mode = MODE_NORMAL;
volatile AlertLevel current_alert = ALERT_NONE;
volatile uint32_t uptime_seconds = 0;
volatile uint8_t pc_connected = 0;   /* heartbeat timeout ile kontrol */
volatile uint32_t last_pc_heartbeat = 0;

/* sensör verileri */
typedef struct {
    uint16_t temperature;  /* 0.1°C çözünürlük */
    uint16_t light;        /* 0-4095 ADC */
    uint16_t distance;     /* mm cinsinden */
    uint16_t pot;          /* 0-4095 ADC */
} SensorData;

SensorData sensors = {0};

/* ========== UART PROTOKOL ========== */
typedef struct {
    uint8_t command;
    uint8_t length;
    uint8_t data[MAX_DATA];
} Packet;

/* paket gönder */
void send_packet(uint8_t cmd, uint8_t *data, uint8_t len) {
    uint8_t crc = cmd ^ len;
    for (int i = 0; i < len; i++) crc ^= data[i];

    uint8_t buf[MAX_DATA + 5];
    buf[0] = START_BYTE;
    buf[1] = cmd;
    buf[2] = len;
    memcpy(&buf[3], data, len);
    buf[3 + len] = crc;
    buf[4 + len] = END_BYTE;

    HAL_UART_Transmit(&huart2, buf, 5 + len, 100);
}

/* heartbeat gönder (her 1 saniye) */
void send_heartbeat(void) {
    uint8_t mode = (uint8_t)current_mode;
    send_packet(CMD_HEARTBEAT, &mode, 1);
}

/* sensör verisi gönder */
void send_sensor_data(void) {
    uint8_t data[8];
    memcpy(&data[0], &sensors.temperature, 2);
    memcpy(&data[2], &sensors.light, 2);
    memcpy(&data[4], &sensors.distance, 2);
    memcpy(&data[6], &sensors.pot, 2);
    send_packet(CMD_SENSOR_DATA, data, 8);
}

/* durum raporu gönder */
void send_status_report(void) {
    uint8_t data[4];
    data[0] = (uint8_t)current_mode;
    data[1] = (uint8_t)current_alert;
    data[2] = (uint8_t)(uptime_seconds & 0xFF);
    data[3] = (uint8_t)((uptime_seconds >> 8) & 0xFF);
    send_packet(CMD_STATUS_REPORT, data, 4);
}

/* gelen paketi işle */
void process_packet(Packet *pkt) {
    switch (pkt->command) {
        case CMD_SET_MODE:
            if (pkt->length >= 1) {
                current_mode = (NodeMode)pkt->data[0];
                /* OLED'de göster */
                update_oled_mode();
                /* onay gönder */
                send_packet(CMD_MODE_ACK, pkt->data, 1);
            }
            break;

        case CMD_REQUEST_STATUS:
            send_status_report();
            break;

        case CMD_SET_ALERT:
            if (pkt->length >= 1) {
                current_alert = (AlertLevel)pkt->data[0];
                update_buzzer();
            }
            break;

        case CMD_DISPLAY_TEXT:
            /* OLED'e yaz */
            oled_clear();
            oled_write_string(0, 0, (char*)pkt->data, pkt->length);
            break;

        case CMD_BUZZER_ON:
            HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
            break;

        case CMD_BUZZER_OFF:
            HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
            break;
    }
}

/* ========== SENSÖR OKUMA ========== */

/* LM35 sıcaklık: Vout = 10mV/°C, ADC 0-4095 = 0-3.3V */
void read_temperature(void) {
    uint32_t adc_val;
    HAL_ADC_Start(&hadc1);
    HAL_ADC_PollForConversion(&hadc1, 100);
    adc_val = HAL_ADC_GetValue(&hadc1);
    /* mV = adc * 3300 / 4095, temp = mV / 10 */
    sensors.temperature = (uint16_t)((adc_val * 3300) / 4095 / 10 * 10);
}

/* HC-SR04 mesafe: trigger → echo süresi → cm */
void read_distance(void) {
    /* 10us trigger pulse */
    HAL_GPIO_WritePin(TRIG_GPIO_Port, TRIG_Pin, GPIO_PIN_SET);
    delay_us(10);
    HAL_GPIO_WritePin(TRIG_GPIO_Port, TRIG_Pin, GPIO_PIN_RESET);

    /* echo süresini ölç */
    uint32_t start = __HAL_TIM_GET_COUNTER(&htim2);
    while (HAL_GPIO_ReadPin(ECHO_GPIO_Port, ECHO_Pin) == GPIO_PIN_RESET);
    start = __HAL_TIM_GET_COUNTER(&htim2);
    while (HAL_GPIO_ReadPin(ECHO_GPIO_Port, ECHO_Pin) == GPIO_PIN_SET);
    uint32_t end = __HAL_TIM_GET_COUNTER(&htim2);

    /* ses hızı: 343 m/s, gidiş-dönüş / 2, us → mm */
    uint32_t duration_us = end - start;
    sensors.distance = (uint16_t)(duration_us * 343 / 2000);
}

/* ========== OLED GÜNCELLEME ========== */
void update_oled_mode(void) {
    oled_clear();
    switch (current_mode) {
        case MODE_NORMAL:
            oled_write_string(0, 0, "SPECTRA", 7);
            oled_write_string(0, 2, "Mode: NORMAL", 12);
            break;
        case MODE_DEGRADED:
            oled_write_string(0, 0, "! DEGRADED !", 12);
            oled_write_string(0, 2, "Reduced comms", 13);
            break;
        case MODE_LOCAL_AUTONOMY:
            oled_write_string(0, 0, "!! LOCAL !!", 11);
            oled_write_string(0, 2, "Autonomous mode", 15);
            break;
        case MODE_SILENT:
            oled_write_string(0, 0, "SILENT", 6);
            oled_write_string(0, 2, "Radio silence", 13);
            break;
        case MODE_EMERGENCY:
            oled_write_string(0, 0, "EMERGENCY!", 10);
            oled_write_string(0, 2, "Critical alert", 14);
            break;
    }
}

/* buzzer alarm seviyesine göre kontrol */
void update_buzzer(void) {
    switch (current_alert) {
        case ALERT_NONE:
        case ALERT_LOW:
            HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
            break;
        case ALERT_MEDIUM:
            /* kısa bip (ana döngüde toggle) */
            break;
        case ALERT_HIGH:
        case ALERT_CRITICAL:
            HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
            break;
    }
}

/* ========== FAIL-OPERATIONAL ========== */
/* PC bağlantısı kesilirse yerel otonom moda geç */
void check_pc_connection(void) {
    if (HAL_GetTick() - last_pc_heartbeat > 5000) {
        /* 5 saniyedir PC'den veri yok */
        pc_connected = 0;
        if (current_mode != MODE_LOCAL_AUTONOMY) {
            current_mode = MODE_LOCAL_AUTONOMY;
            update_oled_mode();
            current_alert = ALERT_HIGH;
            update_buzzer();
        }
    } else {
        pc_connected = 1;
    }
}

/* ========== ANA DÖNGÜ ========== */
/*
int main(void) {
    HAL_Init();
    SystemClock_Config();

    // periferileri başlat
    MX_GPIO_Init();
    MX_ADC1_Init();
    MX_I2C1_Init();
    MX_USART2_UART_Init();
    MX_TIM2_Init();

    oled_init();
    update_oled_mode();

    uint32_t last_heartbeat = 0;
    uint32_t last_sensor = 0;

    while (1) {
        uint32_t now = HAL_GetTick();

        // UART'tan paket oku ve işle
        if (uart_has_packet()) {
            Packet pkt;
            if (uart_parse_packet(&pkt)) {
                last_pc_heartbeat = now;
                process_packet(&pkt);
            }
        }

        // her 1 saniye: heartbeat gönder
        if (now - last_heartbeat >= 1000) {
            last_heartbeat = now;
            uptime_seconds++;
            send_heartbeat();
            check_pc_connection();
        }

        // her 3 saniye: sensör oku ve gönder
        if (now - last_sensor >= 3000) {
            last_sensor = now;
            read_temperature();
            read_distance();
            // LDR ve pot ADC oku
            // ...
            send_sensor_data();
        }

        HAL_Delay(10);
    }
}
*/
