---
name: stm32-hal-development
description: 在 CubeMX 生成的 HAL 工程上开发 STM32 固件。涵盖外设配置、BSP 驱动架构、中断安全代码、硬件感知故障排查。覆盖 UART DMA+IDLE 不定长接收、SPI/I2C 时序、ADC 校准、FreeRTOS 集成。当用户需要 STM32 HAL 实现指导（而非通用 C 语言建议）时使用。触发词：STM32、HAL、CubeMX、STM32Cube、外设初始化、HAL库、STM32开发、STM32外设配置、MX_Init、HAL_Init、STM32项目、stm32工程、HAL实现、HAL配置、STMCube、生成代码、HAL驱动、STM32驱动、STM32F1、STM32F4、STM32H7、STM32G4。
version: "1.0.0"
---

# STM32 HAL Development

Treat this skill as the working playbook for CubeMX-based STM32 projects.

## Workflow

1. Read [references/core-guidelines.md](references/core-guidelines.md) first.
2. Keep all custom code inside `USER CODE` regions unless the project has an explicit non-CubeMX extension point.
3. Configure peripherals in CubeMX, regenerate code, then add application or BSP logic.
4. Read additional references only as needed:
   - [references/peripheral-driver-guide.md](references/peripheral-driver-guide.md) for sensor and bus drivers
   - [references/hal-quick-reference.md](references/hal-quick-reference.md) for API lookups
   - [references/troubleshooting-guide.md](references/troubleshooting-guide.md) for failure analysis
   - [references/usage-examples.md](references/usage-examples.md) for implementation patterns
5. Reuse [assets/bsp-template.c](assets/bsp-template.c) and [assets/bsp-template.h](assets/bsp-template.h) when starting a new BSP module.

## Notes

- Prioritize hardware constraints, interrupt safety, and regeneration safety over local code convenience.
- Do not modify CubeMX-generated initialization files directly when the same change belongs in the `.ioc` configuration.

## 杈圭晫瀹氫箟

### 涓嶈婵€娲?- 鐢ㄦ埛鐨勭洰鏍囪姱鐗囦笉鏄?STM32 绯诲垪锛圗SP32銆乶RF銆丟D32銆丯XP i.MX RT 绛夛級鈫?鏌ユ壘瀵瑰簲骞冲彴鐨勫紑鍙戞寚鍗?- 鐢ㄦ埛闇€瑕佺殑鏄８瀵勫瓨鍣ㄦ搷浣滄垨 LL 搴撳紑鍙戯紙闈?HAL锛?- 鐢ㄦ埛鐨勯」鐩湭浣跨敤 CubeMX 鐢熸垚浠ｇ爜
- 鐢ㄦ埛鍙渶瑕佹煡闃呯壒瀹?HAL API 鐨勫弬鑰冩墜鍐岋紙浣跨敤 hal-quick-reference.md 鍗冲彲锛?
### 涓嶈鍋?- **绂佹**淇敼 CubeMX 鐢熸垚鐨勯潪 USER CODE 鍖哄煙浠ｇ爜锛堜細琚?CubeMX 閲嶆柊鐢熸垚瑕嗙洊锛?- **绂佹**鍦ㄤ腑鏂洖璋冧腑璋冪敤闃诲寮?HAL 鍑芥暟锛氬寘鎷絾涓嶉檺浜?`HAL_Delay`銆乣HAL_UART_Transmit`锛堝惈 `HAL_MAX_DELAY`锛夈€乣HAL_I2C_Master_Transmit` 绛夈€侷SR 鍐呭彧鍏佽缃爣蹇椾綅锛屽疄闄呴€氫俊蹇呴』鍦ㄤ换鍔?涓诲惊鐜腑鎵ц銆傝繚鍙嶆瑙勫垯灏嗗鑷?HAL 鐘舵€佹満鍗℃锛坓State/RxState 姘镐箙閿佹鍦?BUSY 鐘舵€侊級锛屼笖鍚屼紭鍏堢骇 ISR 鍐呰疆璇?TXE/TC 鍙兘姘镐箙闃诲
- **绂佹**寤鸿浣跨敤 `HAL_Init()` 浠ュ鐨勬椂閽熼厤缃柟寮忥紙鏃堕挓鏍戦€氳繃 CubeMX 绠＄悊锛?- **绂佹**缁曞紑 HAL 鐩存帴鎿嶄綔澶栬瀵勫瓨鍣紙闄ら潪鍦?critical section 涓湁鎬ц兘纭渶姹傦紝鎴?STM32F1 鐨?GPIO PULLUP 鍦?HAL 涓棤娉曠敓鏁堝繀椤荤洿鎺ュ啓 CRL/BSRR锛?
### 涓嶈纰?- **涓嶈Е纰?* `.ioc` 鏂囦欢锛氬彧寤鸿閰嶇疆椤癸紝涓嶇洿鎺ヤ慨鏀?XML
- **涓嶈Е纰?* CubeMX 鐢熸垚鐨勯潪 USER CODE 鍖哄煙
- **涓嶈Е纰?* CMSIS Core 鏂囦欢锛坈ore_cm4.h 绛夌郴缁熷ご鏂囦欢锛?
