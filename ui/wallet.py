from pwallet import PersistentWallet
from wallet_controller import WalletController
from wallet_model import AssetDefinition


class Wallet(object):
    def __init__(self):
        self.wallet = PersistentWallet()
        self.wallet.init_model()
        self.model = self.wallet.get_model()
        self.controller = WalletController(self.wallet.get_model())

    def get_asset_definition(self, moniker):
        adm = self.wallet.get_model().get_asset_definition_manager()
        asset = adm.get_asset_by_moniker(moniker)
        if asset:
            return asset
        else:
            raise Exception("asset not found")

    def get_all_monikers(self):
        return [
            asset.get_monikers()[0] for asset in
            self.wallet.get_model().get_asset_definition_manager()
            .get_all_assets()]

    def get_balance(self, color):
        if not isinstance(color, AssetDefinition):
            color = self.get_asset_definition(color)
        return self.controller.get_balance(color)

    def get_all_addresses(self, color):
        if not isinstance(color, AssetDefinition):
            color = self.get_asset_definition(color)
        return [addr.get_address() for addr in
                self.controller.get_all_addresses(color)]

    def send_coins(self, items):
        for item in items:
            self.controller.send_coins(
                item['address'],
                item['asset'] if 'asset' in item
                else self.get_asset_definition(item['moniker']),
                item['value'])

wallet = Wallet()
