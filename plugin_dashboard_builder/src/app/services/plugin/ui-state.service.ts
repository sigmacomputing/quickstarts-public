import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })

export class UiStateService {

    private mainMenuVisible = new BehaviorSubject<boolean>(false); 
    mainMenuVisible$ = this.mainMenuVisible.asObservable();

    setMainMenuVisible(visible: boolean) {
        this.mainMenuVisible.next(visible);
    }

    private legendVisible = new BehaviorSubject<boolean>(false); 
    legendVisible$ = this.legendVisible.asObservable();

    setLegendVisible(visible: boolean) {
        this.legendVisible.next(visible);
    }

    private layerSelectorVisible = new BehaviorSubject<boolean>(false); 
    layerSelectorVisible$ = this.layerSelectorVisible.asObservable();

    setLayerSelectorVisible(visible: boolean) {
        this.layerSelectorVisible.next(visible);
    }

}