use if_addrs::{get_if_addrs, IfAddr};
use serde::Serialize;
use std::net::Ipv4Addr;

#[derive(Clone, Debug, Serialize)]
pub struct LanIp {
    pub name: String,
    pub ip: String,
}

pub fn list_private_ipv4() -> Vec<LanIp> {
    let mut items = get_if_addrs()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|iface| {
            let IfAddr::V4(addr) = iface.addr else {
                return None;
            };
            let ip = addr.ip;
            if is_usable_private(ip) && !is_virtual_name(&iface.name) {
                Some(LanIp {
                    name: iface.name,
                    ip: ip.to_string(),
                })
            } else {
                None
            }
        })
        .collect::<Vec<_>>();

    items.sort_by_key(|item| priority(item.ip.parse().unwrap_or(Ipv4Addr::UNSPECIFIED)));
    items
}

pub fn first_private_ipv4() -> Option<String> {
    list_private_ipv4().into_iter().next().map(|item| item.ip)
}

fn is_usable_private(ip: Ipv4Addr) -> bool {
    !(ip.is_loopback() || ip.is_link_local()) && priority(ip) < 4
}

fn priority(ip: Ipv4Addr) -> u8 {
    let octets = ip.octets();
    match octets {
        [192, 168, _, _] => 0,
        [10, _, _, _] => 1,
        [172, second, _, _] if (16..=31).contains(&second) => 2,
        _ => 4,
    }
}

fn is_virtual_name(name: &str) -> bool {
    let lowered = name.to_ascii_lowercase();
    [
        "vethernet",
        "hyper-v",
        "hyperv",
        "wsl",
        "vmnet",
        "tailscale",
        "utun",
        "tap",
    ]
    .iter()
    .any(|needle| lowered.contains(needle))
}
