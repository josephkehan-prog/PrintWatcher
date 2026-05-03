using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using PrintWatcher.Shell.Models;
using PrintWatcher.Shell.ViewModels;
using Xunit;

namespace PrintWatcher.Shell.Tests;

public sealed class OptionsViewModelTests
{
    [Fact]
    public async Task ChangingProperty_FiresSaveOnce()
    {
        var saves = new List<PrintOptionsDto>();
        var vm = new OptionsViewModel((dto, _) =>
        {
            saves.Add(dto);
            return Task.CompletedTask;
        }, debounceMs: 0);

        vm.Copies = 5;
        await Task.Delay(20); // let the fire-and-forget task settle

        saves.Should().ContainSingle();
        saves[0].Copies.Should().Be(5);
    }

    [Fact]
    public async Task RapidChanges_OnlyLastWinsAfterDebounce()
    {
        var saves = new List<PrintOptionsDto>();
        var vm = new OptionsViewModel((dto, _) =>
        {
            saves.Add(dto);
            return Task.CompletedTask;
        }, debounceMs: 50);

        vm.Copies = 2;
        vm.Copies = 5;
        vm.Copies = 9;
        await Task.Delay(120);

        saves.Should().ContainSingle();
        saves[0].Copies.Should().Be(9);
    }

    [Fact]
    public async Task ApplyOptions_HydratesWithoutFiringSave()
    {
        var saves = new List<PrintOptionsDto>();
        var vm = new OptionsViewModel((dto, _) =>
        {
            saves.Add(dto);
            return Task.CompletedTask;
        }, debounceMs: 0);

        vm.ApplyOptions(new PrintOptionsDto
        {
            Printer = "HP LaserJet",
            Copies = 3,
            Sides = "duplex",
            Color = "monochrome",
        });
        await Task.Delay(20);

        vm.Printer.Should().Be("HP LaserJet");
        vm.Copies.Should().Be(3);
        vm.Sides.Should().Be("duplex");
        vm.Color.Should().Be("monochrome");
        saves.Should().BeEmpty();
    }

    [Fact]
    public void ApplyPrinters_UsesDefaultWhenPrinterUnset()
    {
        var vm = new OptionsViewModel(null);
        vm.ApplyPrinters(new PrintersDto
        {
            Default = "HP LaserJet",
            List = new[] { "HP LaserJet", "Office Color" },
        });

        vm.Printers.Should().BeEquivalentTo(new[] { "HP LaserJet", "Office Color" });
        vm.Printer.Should().Be("HP LaserJet");
    }

    [Fact]
    public void ApplyPrinters_DoesNotOverridePreviousChoice()
    {
        var vm = new OptionsViewModel(null);
        vm.ApplyOptions(new PrintOptionsDto { Printer = "Office Color" });
        vm.ApplyPrinters(new PrintersDto
        {
            Default = "HP LaserJet",
            List = new[] { "HP LaserJet", "Office Color" },
        });

        vm.Printer.Should().Be("Office Color");
    }

    [Fact]
    public void Copies_ClampsToValidRange()
    {
        var vm = new OptionsViewModel(null);
        vm.Copies = 0;
        vm.Copies.Should().Be(1);
        vm.Copies = 200;
        vm.Copies.Should().Be(99);
    }

    [Fact]
    public void CopiesDouble_RoundtripsThroughInt()
    {
        var vm = new OptionsViewModel(null);
        vm.CopiesDouble = 7.6;
        vm.Copies.Should().Be(8);
        vm.CopiesDouble.Should().Be(8.0);
    }
}
