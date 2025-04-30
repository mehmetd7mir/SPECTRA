//
//  LanguageSelectionViewController.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 29.04.2025.
//

import UIKit

class LanguageSelectionViewController: UIViewController {
    
    @IBOutlet private weak var chooseLanguageLabel: UILabel!
    @IBOutlet private weak var spanishButton: UIButton!
    @IBOutlet private weak var italianButton: UIButton!
    @IBOutlet private weak var frenchButton: UIButton!
    @IBOutlet private weak var germanButton: UIButton!
    @IBOutlet private weak var türkishButton: UIButton!
    @IBOutlet private weak var englishButton: UIButton!
    
    private let isNotSelectedImage = UIImage(systemName: "square.fill")
    private let selectedImage = UIImage(systemName: "checkmark.square.fill")
    
    private let languageModel = LanguageSelectionViewModel()
    
    private lazy var buttonList : [UIButton] = []
    
    override func loadView() {
        let nib = UINib(nibName: "LanguageSelectionView", bundle: nil)
        self.view = nib.instantiate(withOwner: self, options: nil).first as? UIView
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        appendButtons()
    }
    
    @IBAction private func languageButtonTapped(_ sender: UIButton) {
        DispatchQueue.main.async {
            for button in self.buttonList {
                button.setImage(self.isNotSelectedImage, for: .normal)
            }
            sender.setImage(self.selectedImage, for: .normal)
            if let key = sender.currentTitle {
                if let code = self.languageModel.languageDict[key] {
                    self.languageModel.saveSelectedLanguage(code: code)
                }
            }
        }
        
    }
    
    private func appendButtons(){
        buttonList.append(englishButton)
        buttonList.append(türkishButton)
        buttonList.append(germanButton)
        buttonList.append(frenchButton)
        buttonList.append(italianButton)
        buttonList.append(spanishButton)
    }
}
