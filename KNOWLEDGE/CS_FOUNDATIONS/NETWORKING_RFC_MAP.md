# COMPUTER SCIENCE FOUNDATIONS: NETWORKING RFC ARCHITECTURE MAP

> **Subsystem:** Carrier-Grade Network Protocol Stack  
> **Target OS:** Rinjani 1.0.0 (Powered by ASL Core Kernel v1.0.0)  
> **Standard:** IETF RFCs / DO-178C DAL-A Deterministic Networking  

---

## 1. Network Stack Architectural Hierarchy

```
+-------------------------------------------------------------------------+
| L7 Application Plane: DHCP Client (RFC 2131) / Serial CLI / Management  |
+-------------------------------------------------------------------------+
| L4 Transport Plane: UDP (RFC 768) / TCP Stream State Machine (RFC 793)  |
+-------------------------------------------------------------------------+
| L3 Network Plane: IPv4 (RFC 791) / ICMP (RFC 792) / TCAM 5-Tuple Engine |
+-------------------------------------------------------------------------+
| L2 Link Layer Plane: Ethernet II (DIX) / ARP (RFC 826) / 802.1Q VLAN    |
+-------------------------------------------------------------------------+
| L1 Physical Driver & Hardware: PCI Config (0xCF8/CFC) / VirtIO-Net / PMD|
+-------------------------------------------------------------------------+
```

---

## 2. Canonical RFC Mapping & Implementation Matrix

| Layer | Protocol | RFC Reference | Peran di ASL Core / Rinjani 1.0.0 | Status Implementasi |
| :--- | :--- | :--- | :--- | :--- |
| **L2** | **Ethernet II** | IEEE 802.3 / DIX v2 | 14-byte frame header (Dst MAC, Src MAC, EtherType). Parsing nol-kopi. | `TEST & RUNTIME VERIFIED` |
| **L2** | **ARP** | **RFC 826** | Resolusi MAC-ke-IP untuk frame ingress & balasan ARP Reply otomatis. | `TEST & RUNTIME VERIFIED` |
| **L3** | **IPv4** | **RFC 791** | Validasi versi (4), IHL, Total Length, Drop fragmen (DF flag), Checksum RFC 1071. | `TEST & RUNTIME VERIFIED` |
| **L3** | **ICMP** | **RFC 792** | Pembangkitan ICMP Echo Reply (Type 0) saat menerima Echo Request (Type 8). | `TEST & RUNTIME VERIFIED` |
| **L4** | **UDP** | **RFC 768** | Port-based datagram demux (8-byte header, length, checksum). | `TEST VERIFIED` |
| **L7** | **DHCP** | **RFC 2131** | Dynamic Host Configuration: DHCP Discover (opt 53), fallback dev-static. | `TEST & RUNTIME VERIFIED` |
| **Aux** | **Internet Checksum** | **RFC 1071** | Algoritma penjumlahan 1's complement 16-bit untuk IPv4, ICMP, dan UDP. | `TEST VERIFIED` |
| **L3** | **IPv4 Subnetting** | **RFC 950 / RFC 1878** | TCAM bitwise masking untuk pencocokan subnet classless (CIDR /24). | `TEST VERIFIED` |

---

## 3. Invariant Protokol Carrier-Grade
1. **Zero Dynamic Allocation:** Buffer paket (`asl-router-netbuf`) dialokasikan pada memory compile-time secara statis. Tidak ada pemanggilan heap selama perutean frame.
2. **Strict Fragment Rejection:** Sesuai standar deterministik avionik, frame IPv4 dengan fragment offset (`flags & 0x3FFF != 0`) langsung di-drop untuk mencegah serangan fragment reassembly resource-exhaustion.
3. **Checksum Recalculation:** Checksum header wajib dihitung ulang secara mutlak pada setiap paket transit maupun balasan lokal.
