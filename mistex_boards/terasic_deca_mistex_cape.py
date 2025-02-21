#!/usr/bin/env python3
#
# This file is part of MiSTeX-Boards.
#
# Copyright (c) 2023 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause
#

from os.path import join
import sys
import yaml

from colorama import Fore, Style

from migen import *
from litex.build.generic_platform import *
from litex_boards.platforms import terasic_deca
from litex.gen import LiteXModule

from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder import Builder
from litex.soc.cores.clock import Max10PLL
from litex.soc.cores.spi.spi_bone import SPIBone

from util import *

# Build --------------------------------------------------------------------------------------------

class Top(SoCCore):
    def __init__(self, platform) -> None:
        sdram       = platform.request("sdram")
        ddram       = platform.request("ddram")
        hps_i2c     = platform.request("hps_i2c")
        hdmi        = platform.request("hdmi")
        hdmi_i2c    = platform.request("hdmi_i2c")
        hdmi_i2s    = platform.request("hdmi_i2s")
        sdcard      = platform.request("sdcard")
        hps_spi     = platform.request("hps_spi")
        hps_control = platform.request("hps_control")

        leds = Signal(8)
        self.comb += Cat([platform.request("user_led", l) for l in range(8)]).eq(~leds)

        clk50 = Signal()
        self.comb += clk50.eq(platform.request("clk50"))

        AW = 26
        DW = 64
        self.debug = False

        self.cd_sys    = ClockDomain()
        self.cd_avalon = ClockDomain()
        sys_clk_freq   = 150e6

        # SoCCore ----------------------------------------------------------------------------------
        kwargs = {}
        kwargs["uart_name"]            = "stub"
        kwargs["cpu_type"]             = "None"
        kwargs["l2_size"]              = 0
        kwargs["bus_data_width"]       = 32
        kwargs["bus_address_width"]    = 32
        kwargs['integrated_rom_size']  = 0x0
        kwargs['integrated_sram_size'] = 0x0
        SoCCore.__init__(self, platform, sys_clk_freq, ident = f"LiteX SoC on MiSTeX / Terasic DECA cape", **kwargs)

        avalon_clock         = Signal()
        avalon_address       = Signal(AW)
        avalon_byteenable    = Signal(DW//8)
        avalon_read          = Signal()
        avalon_readdata      = Signal(DW)
        avalon_burstcount    = Signal(8)
        avalon_write         = Signal()
        avalon_writedata     = Signal(DW)
        avalon_ready         = Signal()
        avalon_readdatavalid = Signal()
        avalon_burstbegin    = Signal()
        avalon_waitrequest   = Signal()

        afi_half_clk = Signal()
        afi_reset_export_n = Signal()
        afi_reset_n = Signal()

        ddr3 = Instance("ddr3",
            i_pll_ref_clk         = clk50,
            i_global_reset_n      = ~ResetSignal(),
            i_soft_reset_n        = ~ResetSignal(),
            o_afi_clk             = avalon_clock,
            o_afi_half_clk        = afi_half_clk,
            o_afi_reset_n         = afi_reset_export_n,
            o_afi_reset_export_n  = afi_reset_n,

            o_mem_a               = ddram.a,
            o_mem_ba              = ddram.ba,
            io_mem_ck             = ddram.clk_p,
            io_mem_ck_n           = ddram.clk_n,
            o_mem_cke             = ddram.cke,
            o_mem_cs_n            = ddram.cs_n,
            o_mem_dm              = ddram.dm,
            o_mem_ras_n           = ddram.ras_n,
            o_mem_cas_n           = ddram.cas_n,
            o_mem_we_n            = ddram.we_n,
            o_mem_reset_n         = ddram.reset_n,
            io_mem_dq             = ddram.dq,
            io_mem_dqs            = ddram.dqs_p,
            io_mem_dqs_n          = ddram.dqs_n,
            o_mem_odt             = ddram.odt,

            o_avl_ready           = avalon_ready,
            i_avl_burstbegin      = avalon_burstbegin,
            i_avl_addr            = avalon_address,
            o_avl_rdata_valid     = avalon_readdatavalid,
            o_avl_rdata           = avalon_readdata,
            i_avl_wdata           = avalon_writedata,
            i_avl_be              = avalon_byteenable,
            i_avl_read_req        = avalon_read,
            i_avl_write_req       = avalon_write,
            i_avl_size            = avalon_burstcount,
            o_local_init_done     = leds[5],
            o_local_cal_success   = leds[6],
            o_local_cal_fail      = leds[7],
            # o_pll_mem_clk         = 
            # o_pll_write_clk       = 
            o_pll_locked          = leds[4],
            # o_pll_capture0_clk    = 
            # o_pll_capture1_clk    = 
        )
        self.specials += ddr3

        self.comb += [
            avalon_burstbegin.eq(avalon_write & avalon_read),
            avalon_waitrequest.eq(~avalon_ready),
            ClockSignal("avalon").eq(avalon_clock),
            ClockSignal().eq(ClockSignal("avalon"))
        ]

        sys_top = Instance("sys_top",
            p_DW            = DW,
            p_AW            = AW,
            i_CLK_50        = clk50,
            # o_CLK_VIDEO     = ClockSignal(),

            # HDMI I2C
            o_HDMI_I2C_SCL  = hdmi_i2c.scl,
            io_HDMI_I2C_SDA = hdmi_i2c.sda,            
            # HDMI I2S
            o_HDMI_MCLK     = hdmi_i2s.mclk,
            o_HDMI_SCLK     = hdmi_i2s.sclk,
            o_HDMI_LRCLK    = hdmi_i2s.lrclk,
            o_HDMI_I2S      = hdmi_i2s.i2s,
            # HDMI VIDEO
            o_HDMI_TX_D     = Cat(hdmi.r, hdmi.g, hdmi.b),
            o_HDMI_TX_CLK   = hdmi.clk,
            o_HDMI_TX_DE    = hdmi.de,
            o_HDMI_TX_HS    = hdmi.hsync,
            o_HDMI_TX_VS    = hdmi.vsync,
            i_HDMI_TX_INT   = hdmi.int,

            # SDRAM
            o_SDRAM_A      = sdram.a,
            io_SDRAM_DQ    = sdram.dq,
            # o_SDRAM_DQML = sdram.dm[0], not connected
            # o_SDRAM_DQMH = sdram.dm[1], not connected
            o_SDRAM_nWE    = sdram.we_n,
            o_SDRAM_nCAS   = sdram.cas_n,
            o_SDRAM_nRAS   = sdram.ras_n,
            o_SDRAM_nCS    = sdram.cs_n,
            o_SDRAM_BA     = sdram.ba,
            o_SDRAM_CLK    = platform.request("sdram_clock"),
            # o_SDRAM_CKE  = sdram.cke, not connected

            # TODO: DAC
            # o_AUDIO_L     = audio.l,
            # o_AUDIO_R     = audio.r,
            # o_AUDIO_SPDIF = audio.spdif,
            # io_SDCD_SPDIF = audio.sbcd_spdif,

            o_LED_USER  = leds[2],
            o_LED_HDD   = leds[1],
            o_LED_POWER = leds[0],
            # i_BTN_USER  = platform.request("user_btn", 0),
            i_BTN_OSD   = platform.request("user_btn", 0),
            i_BTN_RESET = platform.request("user_btn", 1),

            o_SD_SPI_CS   = sdcard.sel,
            i_SD_SPI_MISO = sdcard.data[0],
            o_SD_SPI_CLK  = sdcard.clk,
            o_SD_SPI_MOSI = sdcard.cmd,

            #o_LED = Cat([leds[l]) for led in range(3, 5)]),

            i_HPS_SPI_MOSI = hps_spi.mosi,
            o_HPS_SPI_MISO = hps_spi.miso,
            i_HPS_SPI_CLK = hps_spi.clk,
            i_HPS_SPI_CS = hps_spi.cs_n,

            i_HPS_FPGA_ENABLE = hps_control.fpga_enable,
            i_HPS_OSD_ENABLE = hps_control.osd_enable,
            i_HPS_IO_ENABLE = hps_control.io_enable,
            i_HPS_CORE_RESET = hps_control.core_reset,
            # o_DEBUG = N/C

            i_ddr3_clk_i           = avalon_clock,
            o_ddr3_address_o       = avalon_address,
            o_ddr3_byteenable_o    = avalon_byteenable,
            o_ddr3_read_o          = avalon_read,
            i_ddr3_readdata_i      = avalon_readdata,
            o_ddr3_burstcount_o    = avalon_burstcount,
            o_ddr3_write_o         = avalon_write,
            o_ddr3_writedata_o     = avalon_writedata,
            i_ddr3_waitrequest_i   = avalon_waitrequest,
            i_ddr3_readdatavalid_i = avalon_readdatavalid,
        )
        self.specials += sys_top

        if self.debug:
            # SPIBone ----------------------------------------------------------------------------------
            self.submodules.spibone = spibone = SPIBone(platform.request("spibone"))
            self.add_wb_master(spibone.bus)

            from litescope import LiteScopeAnalyzer
            analyzer_signals = [
                # DBus (could also just added as self.cpu.dbus)
                avalon_clock,
                avalon_address,
                avalon_waitrequest,
                avalon_read,
                #avalon_readdata,
                avalon_readdatavalid,
                avalon_write,
                #avalon_writedata,
                avalon_burstcount,
                avalon_byteenable,
            ]
            self.analyzer = LiteScopeAnalyzer(analyzer_signals,
                depth        = 4096,
                samplerate   = 150e6,
                clock_domain = "sys",
                csr_csv      = "analyzer.csv")


def main(core):
    coredir = join("cores", core)

    mistex_yaml = yaml.load(open(join(coredir, "MiSTeX.yaml"), 'r'), Loader=yaml.FullLoader)

    platform = terasic_deca.Platform()

    add_designfiles(platform, coredir, mistex_yaml, 'quartus')

    generate_build_id(platform, coredir)
    add_mainfile(platform, coredir, mistex_yaml)

    platform.add_platform_command(f"set_global_assignment -name QIP_FILE {os.getcwd()}/rtl/deca-ddr3/ddr3.qip")
    platform.add_platform_command("set_global_assignment -name TIMEQUEST_MULTICORNER_ANALYSIS OFF")
    platform.add_platform_command("set_global_assignment -name OPTIMIZE_POWER_DURING_FITTING OFF")
    platform.add_platform_command("set_global_assignment -name FINAL_PLACEMENT_OPTIMIZATION ALWAYS")
    platform.add_platform_command("set_global_assignment -name FITTER_EFFORT \"STANDARD FIT\"")
    platform.add_platform_command("set_global_assignment -name OPTIMIZATION_MODE \"HIGH PERFORMANCE EFFORT\"")
    platform.add_platform_command("set_global_assignment -name ALLOW_POWER_UP_DONT_CARE ON")
    platform.add_platform_command("set_global_assignment -name QII_AUTO_PACKED_REGISTERS \"SPARSE AUTO\"")
    platform.add_platform_command("set_global_assignment -name ROUTER_LCELL_INSERTION_AND_LOGIC_DUPLICATION ON")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_COMBO_LOGIC ON")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_EFFORT EXTRA")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_REGISTER_DUPLICATION ON")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_REGISTER_RETIMING ON")
    platform.add_platform_command("set_global_assignment -name OPTIMIZATION_TECHNIQUE SPEED")
    platform.add_platform_command("set_global_assignment -name MUX_RESTRUCTURE ON")
    platform.add_platform_command("set_global_assignment -name REMOVE_REDUNDANT_LOGIC_CELLS ON")
    platform.add_platform_command("set_global_assignment -name AUTO_DELAY_CHAINS_FOR_HIGH_FANOUT_INPUT_PINS ON")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_COMBO_LOGIC_FOR_AREA ON")
    platform.add_platform_command("set_global_assignment -name ADV_NETLIST_OPT_SYNTH_WYSIWYG_REMAP ON")
    platform.add_platform_command("set_global_assignment -name SYNTH_GATED_CLOCK_CONVERSION ON")
    platform.add_platform_command("set_global_assignment -name PRE_MAPPING_RESYNTHESIS ON")
    platform.add_platform_command("set_global_assignment -name ROUTER_CLOCKING_TOPOLOGY_ANALYSIS ON")
    platform.add_platform_command("set_global_assignment -name ECO_OPTIMIZE_TIMING ON")
    platform.add_platform_command("set_global_assignment -name PERIPHERY_TO_CORE_PLACEMENT_AND_ROUTING_OPTIMIZATION ON")
    platform.add_platform_command("set_global_assignment -name PHYSICAL_SYNTHESIS_ASYNCHRONOUS_SIGNAL_PIPELINING ON")
    platform.add_platform_command("set_global_assignment -name ALM_REGISTER_PACKING_EFFORT LOW")
    platform.add_platform_command("set_global_assignment -name OPTIMIZE_POWER_DURING_SYNTHESIS OFF")
    platform.add_platform_command("set_global_assignment -name ROUTER_REGISTER_DUPLICATION ON")
    platform.add_platform_command("set_global_assignment -name FITTER_AGGRESSIVE_ROUTABILITY_OPTIMIZATION ALWAYS")
    platform.add_platform_command("set_global_assignment -name SEED 1")

    defines = mistex_yaml.get('defines', {})
    defines.update({
        "ALTERA": 1,
        # prevent the OSD header from covering the menu
        "OSD_HEADER": 1,
        "CRG_AUDIO_CLK": 1,
        "HARDWARE_HDMI_INIT": 1,
        "NO_SCANDOUBLER": 1,
        "DISABLE_VGA": 1,
        "SKIP_SHADOWMASK": 1,
        "SKIP_IIR_FILTER": 1,
        # "SKIP_ASCAL": 1,
        # "MISTER_DISABLE_ADAPTIVE": 1,
        # "MISTER_SMALL_VBUF": 1,
        "MISTER_DISABLE_YC": 1,
        "MISTER_DISABLE_ALSA": 1,
    })

    for key, value in defines.items():
        platform.add_platform_command(f'set_global_assignment -name VERILOG_MACRO "{key}={value}"')

    platform.add_extension([
        ("hps_i2c", 0,
            Subsignal("sda", Pins("P9:26")),
            Subsignal("scl", Pins("P9:27")),
            IOStandard("3.3-V LVTTL"),
        ),
        ("hps_spi", 0,
            Subsignal("mosi", Pins("P9:23")),
            Subsignal("miso", Pins("P9:24")),
            Subsignal("clk",  Pins("P9:22")),
            Subsignal("cs_n", Pins("P9:21")),
            IOStandard("3.3-V LVTTL"),
        ),
        ("hps_control", 0,
            Subsignal("fpga_enable", Pins("P9:18")),
            Subsignal("osd_enable",  Pins("P9:19")),
            Subsignal("io_enable",   Pins("P9:20")),
            Subsignal("core_reset",  Pins("P9:17")),
            IOStandard("3.3-V LVTTL"),
        ),
        ("sdram_clock", 0, Pins("P8:22"), IOStandard("3.3-V LVTTL")),
        ("sdram", 0,
            Subsignal("a",     Pins(
                "P8:39 P8:40 P8:41 P8:42 P8:30 P8:27 P8:28 P8:25", 
                "P8:26 P8:23 P8:38 P8:24 P8:21")),
            Subsignal("ba",    Pins("P8:36 P8:37")),
            Subsignal("cs_n",  Pins("P8:35")),
            #Subsignal("cke",   Pins("N/C")), 
            Subsignal("ras_n", Pins("P8:34")),
            Subsignal("cas_n", Pins("P8:33")),
            Subsignal("we_n",  Pins("P8:29")),
            Subsignal("dq", Pins(
                "P8:3  P8:4  P8:5  P8:6  P8:7  P8:8  P8:9  P8:10 ",
                "P8:20 P8:19 P8:18 P8:17 P8:16 P8:15 P8:12 P8:11")),
            #Subsignal("dm", Pins("N/C")),
            IOStandard("3.3-V LVTTL")
        ),
        ("spibone", 0,
            Subsignal("clk",  Pins("P8:13")),
            Subsignal("mosi", Pins("P8:31")),
            Subsignal("miso", Pins("P8:43")),
            Subsignal("cs_n", Pins("P9:41")),
            IOStandard("3.3-V LVCMOS")),
    ])

    build_dir  = get_build_dir(core)
    build_name = get_build_name(core)

    builder = Builder(Top(platform),
        build_backend="litex",
        gateware_dir=build_dir,
        software_dir=os.path.join(build_dir, 'software'),
        compile_gateware=True,
        compile_software=True,
        csr_csv="csr.csv",
        #bios_console="lite"
    )

    builder.build(build_name = get_build_name(core))

    os.system(f"quartus_cpf -c -q 24.0MHz -g 3.3 -n p {build_dir}/{build_name}.sof {build_dir}/{build_name}.svf")

if __name__ == "__main__":
    handle_main(main)
